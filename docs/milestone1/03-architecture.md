# Architecture

## Design goals and constraints

Four constraints shape the architecture — three from the project brief, one from the deployment
target.

1. **Exactly one external entrypoint.** All internal traffic uses `ClusterIP`; precisely one
   Service is reachable from outside the cluster.
2. **At least one multi-container pod**, with a defensible reason for co-location rather than
   separate Deployments.
3. **One credible scaling target**, run at three or more replicas and shown to self-heal.
4. **Single-node Minikube.** No cloud load-balancer controller and no multi-node scheduling, so
   Service types and volume access modes are chosen for what exists on one node rather than for a
   managed cluster.

Two principles follow. **Each service is one transform behind one HTTP contract**, so it can be
exercised with a single `curl` command while the rest of the system is down. **Persistent state has
exactly one owner**, which keeps every scaling and failure question in the system a stateless one.

## Component decomposition

The pipeline is four Deployments. Table 1 lists them with their replica counts at Milestone 2 and
their responsibilities.

| Component | Containers | Replicas | Port(s) | Responsibility |
|:-----------|:----:|:----:|:--------|:---------------------------------------------|
| `gateway` | 1 | 1 | 8080 | Sole external entrypoint. Validates the upload, orchestrates the three internal hops, returns the prediction, serves retrieval. |
| `preprocess` | 1 | 2 | 8081 | Decodes the image, strips EXIF, resizes to 224×224, normalizes to model input. Pillow. |
| `inference` | **2** | **3** | 8082, 9100 | MobileNetV2 forward pass via ONNX Runtime, returns top-*k* labels. Carries the metrics sidecar. |
| `storage` | 1 | 1 (pinned) | 8083 | Owns the only PersistentVolumeClaim. Persists original images, processed images, and prediction JSON. |

: **Component list.** The inference pod is the only multi-container pod. Replica counts are the Milestone 2 targets.

**Why a separate gateway.** The obvious alternative is a chain: expose the preprocessor, have it
call inference, have inference call storage. That removes a pod and a network hop. It was rejected
for two reasons. First, it gives the preprocessor two unrelated jobs — image transformation and
request orchestration — which makes it the hardest service to test and the one most likely to
change for reasons unrelated to preprocessing. Second, retrieval has nowhere sensible to live: the
storage service would have to be exposed externally, which breaks constraint 1 and puts the
component holding all persistent state directly on the public surface. A dedicated gateway keeps
preprocessing and inference as pure functions of their input and leaves exactly one component with
any knowledge of the pipeline's shape.

**Why preprocessing is a service rather than library code in the gateway.** It is the stage most
likely to change — input size, normalization, and model family all land here — and it is CPU-bound
where the gateway is I/O-bound. Separating them lets preprocessing be scaled or replaced without
redeploying the public endpoint. It runs two replicas so the gateway always has a second instance
to fail over to.

## The multi-container pod: inference and its metrics sidecar

The `inference` pod runs two containers (Figure 2):

- **`inference`** — the FastAPI application. On each request it appends one JSON line to
  `requests.jsonl` on a shared volume mounted at `/var/log/app/`, recording the timestamp,
  request ID, latency in milliseconds, model version, and outcome.
- **`metrics-exporter`** — a sidecar that tails that same file, maintains a rolling aggregate
  (request count, error count, p50 and p95 latency), and serves it in Prometheus text format on
  port 9100.

The two containers share an `emptyDir` volume mounted at `/var/log/app/` and communicate over
`localhost`. This is the canonical justification for co-location rather than separation: the
sidecar needs filesystem access to a file the application writes and must observe *this specific
replica*, not the tier in aggregate. Two separate Deployments physically cannot share an
`emptyDir`, and routing through a Service would destroy the per-replica attribution that makes the
metrics useful.

Placing the sidecar on `inference` rather than on the gateway is deliberate. `inference` is the
component being scaled, so every new replica brings its own exporter. That turns the Milestone 2
scaling demonstration from an assertion into an observation: with three replicas, three distinct
`:9100` endpoints report non-zero and roughly balanced request counts, which is direct evidence
that the Service is load-balancing rather than pinning traffic to one pod. An access-logging
sidecar on the single-replica gateway was considered and rejected — it would have produced a
weaker demonstration of why pods group containers at all.

The sidecar is also where the design accepts a known limitation: it aggregates in memory, so its
counters reset when the pod restarts, and there is no Prometheus server scraping it in this
project. Metrics are read directly with `kubectl port-forward` and `curl`. Adding a real
monitoring stack is listed as a next step rather than claimed as a feature.

![**The multi-container inference pod.** The two containers share an `emptyDir` volume and the pod's network namespace, which is precisely why they belong in one pod rather than two Deployments. Each of the three replicas carries its own exporter, so per-pod request counts are directly observable.](docs/diagrams/out/sidecar.pdf){width=92%}

\FloatBarrier

## Service topology and external exposure

| Service | Type | Port mapping | Rationale |
|:---------------|:-----------|:---------------|:--------------------------------------|
| `gateway-svc` | **NodePort** | 30080 → 8080 | The single external entrypoint. Minikube has no cloud load-balancer controller, so a `LoadBalancer` Service would sit in `Pending` indefinitely; NodePort is the honest choice for this target, and `minikube service gateway-svc --url` yields a stable address for testing. |
| `preprocess-svc` | ClusterIP | 8081 → 8081 | Internal only. Also load-balances the two preprocessing replicas. |
| `inference-svc` | ClusterIP | 8082 → 8082, 9100 → 9100 | Internal only. Distributes requests across the three inference replicas; the metrics port is exposed on the Service for convenience but is reached in practice per-pod. |
| `storage-svc` | ClusterIP | 8083 → 8083 | Internal only, and reachable from the gateway alone. The component holding all persistent state is never on the public surface. |

: **Service choices.** Only `gateway-svc` is reachable from outside the cluster.

Services are addressed by DNS name, not IP — `http://preprocess-svc.imgpipe.svc.cluster.local:8081`
— so no manifest contains a hard-coded pod address and rescheduling requires no configuration
change. Figure 3 shows the full topology, including which objects sit inside the cluster boundary.

![**Kubernetes topology.** Boxes are containers; outlined regions are pods with their replica counts. Services appear as the labelled arrows between pods — only `gateway-svc` crosses the cluster edge. Full Service details are in Table 2.](docs/diagrams/out/k8s-topology.pdf){width=86%}

\FloatBarrier

## Request lifecycle and timeout budget

A classification request proceeds through four stages. The gateway generates an `X-Request-Id` on
arrival and propagates it to every downstream call, so a single request can be traced across all
four services' logs.

1. **Validate** — content type against an allowlist, and size against an 8 MB limit, both before
   the body is read into memory.
2. **Preprocess** — `POST /preprocess` with the raw bytes; receives a 224×224 JPEG back.
3. **Infer** — `POST /predict` with the processed image; receives top-*k* labels and scores.
4. **Persist** — three calls to the storage service: the original, the processed image, and the
   prediction JSON. Then respond to the client.

Each hop has an explicit timeout, and the sum of the internal budgets is strictly less than the
client-facing budget so that a slow dependency produces a clean error rather than a connection
reset:

| Stage | Timeout budget | Retry policy |
|:--------------------|:--------|:-------------------------------------------------|
| Client ↔ gateway | 30 s | None — the client owns retries. |
| Gateway → preprocess | 5 s | One retry, connection errors only. |
| Gateway → inference | 15 s | **No retry.** A 5xx from inference is returned as 502; retrying a request that may have been expensive to fail is how a slow tier becomes a dead one. |
| Gateway → storage | 5 s | One retry, connection errors only. |

: **Timeout budget.** These are *design targets*, not measured latencies. No figure in this table has been benchmarked.

Retrying only on connection errors — never on a 5xx — is a deliberate choice. A connection error
means the request never arrived and is safe to repeat; a 5xx means it arrived and failed, and
repeating it multiplies load on a component that is already struggling.

## Scaling target

**`inference` is the scaling target**, running three replicas at Milestone 2. It is the right
choice on three grounds: it is stateless, so replicas are interchangeable; it is CPU-bound on the
ONNX forward pass, which is the single most expensive operation in the request path; and it
therefore holds the largest share of the latency budget (15 s of 30 s), making it the component
that saturates first under concurrent load.

The other three tiers are deliberately not scaled. `gateway` stays at one replica because it is
I/O-bound and not the bottleneck; scaling it would add capacity where none is needed.
`preprocess` runs two replicas for availability rather than throughput. `storage` is **pinned to
one replica** by the ReadWriteOnce access mode of its volume, with `strategy: Recreate` rather
than `RollingUpdate` — a rolling update would attempt to schedule a second pod against a volume
that can only be attached once, and would stall on multi-attach. This is a real constraint of the
design, not an oversight, and §5.3 sets out what it costs and what would relieve it.

## The central tradeoff: synchronous orchestration

The most consequential decision in this design is that classification is **synchronous**. The
gateway holds the client connection open for the entire pipeline and returns the prediction in the
response to the upload.

The alternative is a queue: accept the upload, return `202 Accepted` with a job identifier, have
worker pods consume from a broker, and let the client poll. That design is strictly better under
load. It absorbs traffic spikes in the queue instead of in timeouts, it lets the inference tier be
scaled by queue depth, and it survives a total inference outage without failing user requests.

It was rejected because it would relocate the project's difficulty. A queue introduces a broker
pod, at-least-once delivery, idempotency on retried jobs, job-state storage, and client polling
logic — a substantial body of distributed-systems work that would consume the implementation time
this project is meant to spend on Kubernetes orchestration itself. The synchronous design makes
the failure modes visible and bounded instead: the timeout budget in Table 3 is the entire
back-pressure mechanism, and when inference is unavailable the gateway fails fast with a 503.

The honest cost is stated plainly: **KubeBalancer has no back-pressure beyond its timeouts.**
Under sustained concurrent load past the inference tier's capacity, requests will time out rather
than queue. Moving to a queue-backed design is the first item in the Milestone 3 next-steps
section.

## Resilience and resource policy

- **Probes.** Every service exposes `/healthz` for liveness and `/readyz` for readiness as separate
  endpoints. The distinction matters most on `inference`, where `/readyz` returns 200 only once the
  ONNX model is loaded. Without it, the Service routes traffic to a pod that is running but cannot
  yet answer, producing spurious 503s on every scale-up and restart.
- **Resources.** Inference containers request 256 Mi / 250 m, limited to 768 Mi / 1000 m, with
  `OMP_NUM_THREADS=1`: ONNX Runtime otherwise sizes its thread pool to the host core count, and
  three full-width pools on one node contend badly. Other services request 64 Mi / 50 m, limited to
  256 Mi / 500 m.
- **Images.** Explicit version tags (`kubebalancer/inference:0.1.0`), never `latest`; built locally,
  loaded with `minikube image load`, and `imagePullPolicy: IfNotPresent` so the cluster never
  reaches for a registry that has no copy. MobileNetV2 weights are baked into the image rather than
  fetched by an init container, removing network dependency from pod startup.

## Namespace, labels, and repository layout

All objects live in a dedicated `imgpipe` namespace, which makes teardown unambiguous. Every
object carries the standard recommended labels (`app.kubernetes.io/name`, `/component`,
`/part-of: kubebalancer`, `/version`), so `kubectl` selectors and Service definitions stay
consistent.

Manifests are numerically prefixed so `kubectl apply -f .` applies them in dependency order —
namespace, configuration, volume claims, Deployments, Services. This is what makes the
reproducibility requirement (`kubectl delete -f . && kubectl apply -f .`) work without manual
sequencing:

```
deployments/   00-namespace.yaml  10-gateway.yaml  11-preprocess.yaml
               12-inference.yaml (2 containers)    13-storage.yaml
services/      20-gateway-svc.yaml (NodePort)      21-preprocess-svc.yaml
               22-inference-svc.yaml               23-storage-svc.yaml
storage/       05-storage-pvc.yaml                 (05-storage-pv.yaml, static fallback)
services-src/  gateway/  preprocess/  inference/  metrics-sidecar/  storage/
```

These directories are created in Milestone 2; the layout is fixed here so the report, the
repository, and the test scripts agree from the start.
