#!/usr/bin/env bash
# Capture the Milestone 2 operational evidence: overview, scaling, self-healing,
# scale-to-zero, load balancing across replicas, and a full teardown/rebuild.
#
#   GATEWAY_URL=http://<node-ip>:30080 scripts/evidence.sh [cluster-name]
#
# Each step's commands and output are saved to docs/evidence/m2/<cluster-name>/NN-*.txt
# (cluster-name defaults to "minikube"; use "fabric" for the submitted run).
# Set SKIP_REBUILD=1 to skip the last step, which deletes and re-creates the whole stack.
set -euo pipefail

NS=imgpipe
CLUSTER="${1:-minikube}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/evidence/m2/$CLUSTER"
: "${GATEWAY_URL:?Set GATEWAY_URL to the gateway NodePort, e.g. http://<node-ip>:30080}"
GATEWAY_URL="${GATEWAY_URL%/}"
INFERENCE=app.kubernetes.io/component=inference

WORK="$(mktemp -d)"
BG_PIDS=()
cleanup() {
  for pid in "${BG_PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  rm -rf "$WORK"
}
trap cleanup EXIT
python3 "$ROOT/scripts/make-test-images.py" "$WORK/in"
IMAGE="$WORK/in/sample.png"
mkdir -p "$OUT"

LOG=/dev/null
step() {  # step <file-stem> <title>: start a new evidence file
  LOG="$OUT/$1.txt"
  printf '# %s\n# cluster: %s   captured: %s\n' "$2" "$CLUSTER" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOG"
  printf '\n=== %s ===\n' "$2"
}
say() { printf '\n%s\n' "$*" | tee -a "$LOG"; }
run() {  # run <cmd...>: echo the command like a terminal, then its output
  printf '\n$ %s\n' "$*" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
}
upload() {  # one upload; prints "<status> <inference pod>"
  local body
  body="$(curl -s -m 35 -w '\n%{http_code}' -F "file=@$IMAGE" -F source=test "$GATEWAY_URL/api/v1/images")" || true
  local code="${body##*$'\n'}"
  local pod
  pod="$(printf '%s' "${body%$'\n'*}" | sed -n 's/.*"inferencePod":"\([^"]*\)".*/\1/p')"
  echo "$code ${pod:--}"
}
inference_pods() { kubectl -n "$NS" get pods -l "$INFERENCE" -o jsonpath='{.items[*].metadata.name}'; }
wait_for_pod_count() {  # Terminating pods still count until they are gone.
  for _ in $(seq 120); do
    [[ "$(inference_pods | wc -w)" -eq "$1" ]] && return 0
    sleep 1
  done
  echo "timed out waiting for $1 inference pods" >&2
  return 1
}

# --- 00: environment ---------------------------------------------------------------------
step 00-environment "Cluster and client versions"
run kubectl version
run kubectl get nodes -o wide

# --- 01: everything that is deployed -------------------------------------------------------
step 01-overview "Deployments, pods and Services (kubectl get deploy,pods,svc)"
run kubectl -n "$NS" get deploy,pods,svc -o wide

# --- 02: scaling (T10) ---------------------------------------------------------------------
step 02-scaling "Scaling the inference Deployment 3 -> 1 -> 3 (T10)"
run kubectl -n "$NS" scale deploy/inference --replicas=1
run kubectl -n "$NS" rollout status deploy/inference --timeout=120s
wait_for_pod_count 1
run kubectl -n "$NS" get deploy/inference
run kubectl -n "$NS" get pods -l "$INFERENCE" -o wide
run kubectl -n "$NS" scale deploy/inference --replicas=3
run kubectl -n "$NS" rollout status deploy/inference --timeout=120s
run kubectl -n "$NS" get deploy/inference
run kubectl -n "$NS" get pods -l "$INFERENCE" -o wide

# --- 03: self-healing (T9) -----------------------------------------------------------------
step 03-self-healing "Deleting an inference pod while traffic flows (T9)"
say "Background traffic: one upload every 0.25 s while the pod is deleted and replaced."
( while true; do upload; sleep 0.25; done ) > "$WORK/traffic.txt" &
BG_PIDS+=($!)
sleep 2
victim="$(inference_pods | awk '{print $1}')"
run kubectl -n "$NS" get pods -l "$INFERENCE" -o wide
run kubectl -n "$NS" delete pod "$victim" --wait=false
say "Watching the ReplicaSet replace it (20 s):"
printf '\n$ kubectl -n %s get pods -l %s -o wide --watch\n' "$NS" "$INFERENCE" | tee -a "$LOG"
timeout 20 kubectl -n "$NS" get pods -l "$INFERENCE" -o wide --watch 2>&1 | tee -a "$LOG" || true
run kubectl -n "$NS" rollout status deploy/inference --timeout=120s
run kubectl -n "$NS" get pods -l "$INFERENCE" -o wide
kill "${BG_PIDS[-1]}" 2>/dev/null || true
say "Uploads during the deletion, by HTTP status:"
awk '{print $1}' "$WORK/traffic.txt" | sort | uniq -c | tee -a "$LOG"
run kubectl -n "$NS" get events --field-selector reason=SuccessfulCreate --sort-by=.lastTimestamp

# --- 04: scale to zero (T8) ----------------------------------------------------------------
step 04-scale-to-zero "Inference scaled to 0: the gateway fails fast with 503, then recovers (T8)"
run kubectl -n "$NS" scale deploy/inference --replicas=0
run kubectl -n "$NS" wait --for=delete pod -l "$INFERENCE" --timeout=90s
printf '\n$ curl -F file=@sample.png %s/api/v1/images\n' "$GATEWAY_URL" | tee -a "$LOG"
curl -s -m 35 -w '\nHTTP %{http_code} in %{time_total} s\n' -F "file=@$IMAGE" -F source=test "$GATEWAY_URL/api/v1/images" | tee -a "$LOG"
run kubectl -n "$NS" scale deploy/inference --replicas=3
run kubectl -n "$NS" rollout status deploy/inference --timeout=120s
printf '\n$ curl -F file=@sample.png %s/api/v1/images\n' "$GATEWAY_URL" | tee -a "$LOG"
curl -s -m 35 -o /dev/null -w 'HTTP %{http_code} in %{time_total} s\n' -F "file=@$IMAGE" -F source=test "$GATEWAY_URL/api/v1/images" | tee -a "$LOG"

# --- 05: load balancing and concurrency (T10, T13) -----------------------------------------
step 05-load-balancing "30 uploads, 10 at a time, spread over the inference replicas (T10, T13)"
say "Pods were just recreated in step 04, so each sidecar starts near zero."
# A pod counts as Ready slightly before kube-proxy routes to it; wait until the Service lists all
# three replicas as ready endpoints, then give kube-proxy a moment, so no replica is skipped.
for _ in $(seq 60); do
  ready="$(kubectl -n "$NS" get endpointslices -l kubernetes.io/service-name=inference-svc \
    -o jsonpath='{range .items[*].endpoints[?(@.conditions.ready==true)]}{.addresses[0]}{"\n"}{end}' | grep -c .)"
  [[ "$ready" -ge 3 ]] && break
  sleep 1
done
sleep 3
run kubectl -n "$NS" get endpointslices -l kubernetes.io/service-name=inference-svc
export -f upload
export GATEWAY_URL IMAGE
seq 30 | xargs -P 10 -I{} bash -c upload > "$WORK/burst.txt"
say "HTTP status of the 30 uploads:"
awk '{print $1}' "$WORK/burst.txt" | sort | uniq -c | tee -a "$LOG"
say "Inference pod that served each upload (from the gateway response):"
awk '{print $2}' "$WORK/burst.txt" | sort | uniq -c | tee -a "$LOG"
say "Each replica's metrics-exporter sidecar, read through kubectl port-forward:"
port=19100
for pod in $(inference_pods); do
  kubectl -n "$NS" port-forward "pod/$pod" "$port:9100" >/dev/null 2>&1 &
  pf=$!
  for _ in $(seq 20); do curl -s -o /dev/null "http://127.0.0.1:$port/healthz" && break; sleep 0.25; done
  printf '\n$ kubectl -n %s port-forward pod/%s %s:9100 & curl localhost:%s/metrics\n' "$NS" "$pod" "$port" "$port" | tee -a "$LOG"
  curl -s "http://127.0.0.1:$port/metrics" | grep -v '^#' | tee -a "$LOG"
  kill "$pf" 2>/dev/null || true
  port=$((port + 1))
done

# --- 06: teardown and rebuild (T12) --------------------------------------------------------
if [[ "${SKIP_REBUILD:-0}" != "1" ]]; then
  step 06-rebuild "kubectl delete -f, then kubectl apply -f: the stack comes back with no manual steps (T12)"
  run kubectl delete -f "$ROOT/deployments/" -f "$ROOT/services/" --wait=true
  run kubectl apply -f "$ROOT/deployments/" -f "$ROOT/services/"
  for d in gateway preprocess inference storage; do
    run kubectl -n "$NS" rollout status "deploy/$d" --timeout=180s
  done
  run kubectl -n "$NS" get deploy,pods,svc -o wide
  # The Service was re-created, which ends a `minikube service` tunnel; reach the gateway
  # through a port-forward instead so this works on any cluster.
  kubectl -n "$NS" port-forward svc/gateway-svc 18080:8080 >/dev/null 2>&1 &
  BG_PIDS+=($!)
  for _ in $(seq 40); do curl -s -o /dev/null http://127.0.0.1:18080/healthz && break; sleep 0.25; done
  # Pods can be Ready a moment before kube-proxy has programmed the new Services, so the
  # first uploads may get a fast 503. Wait for a successful upload and record how long it took.
  start=$SECONDS
  until [[ "$(GATEWAY_URL=http://127.0.0.1:18080 upload | cut -d' ' -f1)" == 200 ]]; do
    (( SECONDS - start < 60 )) || { say "No successful upload within 60 s"; break; }
    sleep 1
  done
  say "First successful upload $((SECONDS - start)) s after all Deployments reported ready."
  say "Smoke test against the rebuilt stack:"
  GATEWAY_URL=http://127.0.0.1:18080 "$ROOT/scripts/smoke.sh" 2>&1 | tee -a "$LOG"
fi

printf '\nEvidence written to %s\n' "$OUT"
