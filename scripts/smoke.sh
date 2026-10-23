#!/usr/bin/env bash
# API smoke test through the external Service: the M2 cases from the M1 test matrix (Table 9).
#
#   GATEWAY_URL=http://<node-ip>:30080 scripts/smoke.sh
#
# Minikube with the docker driver on Linux (Docker Desktop) cannot reach the node IP; open a
# tunnel in another terminal with `minikube service gateway-svc -n imgpipe --url` and use its URL.
# Needs bash, curl and python3 (standard library only). Exits non-zero if any check fails.
set -uo pipefail

if [[ -z "${GATEWAY_URL:-}" ]]; then
  if command -v minikube >/dev/null; then
    GATEWAY_URL="http://$(minikube ip):30080"
  else
    echo "Set GATEWAY_URL, e.g. GATEWAY_URL=http://localhost:30080 $0" >&2
    exit 2
  fi
fi
GATEWAY_URL="${GATEWAY_URL%/}"
API="$GATEWAY_URL/api/v1"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 "$(dirname "$0")/make-test-images.py" "$WORK/in"

passed=0
failed=0

check() {  # check <id> <description> <expected> <actual> [detail]
  if [[ "$3" == "$4" ]]; then
    printf 'PASS  %-4s %-44s %s %s\n' "$1" "$2" "$4" "${5:-}"
    passed=$((passed + 1))
  else
    printf 'FAIL  %-4s %-44s expected %s, got %s %s\n' "$1" "$2" "$3" "$4" "${5:-}"
    failed=$((failed + 1))
  fi
}

# upload <file> [filename-to-send]  -> prints "<status> <seconds>", body in $WORK/body
upload() {
  curl -s -m 35 -o "$WORK/body" -w '%{http_code} %{time_total}' \
    -F "file=@$1${2:+;filename=$2}" -F source=test "$API/images"
}

json() {  # json <file> <python expression on d>
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1" 2>/dev/null
}

get() {  # get <url> <output file>  -> prints status
  curl -s -m 10 -o "$2" -w '%{http_code}' "$1"
}

echo "Gateway: $GATEWAY_URL"
echo

# T1: happy path (PNG), then retrieval of everything that was stored.
read -r code secs < <(upload "$WORK/in/sample.png")
cp "$WORK/body" "$WORK/t1.json"
id="$(json "$WORK/t1.json" 'd["imageId"]')"
check T1 "Upload PNG -> prediction" 200 "$code" "($(json "$WORK/t1.json" 'd["label"]'), ${secs}s, pod $(json "$WORK/t1.json" 'd["servedBy"]["inferencePod"]'))"
# The deployment runs the real model; set EXPECT_MOCK=True when testing with MOCK_MODE=1.
check T1 "Prediction is real (not mock)" "${EXPECT_MOCK:-False}" "$(json "$WORK/t1.json" 'd["mock"]')" \
  "($(json "$WORK/t1.json" 'd["modelVersion"]'))"

check T1 "GET /results/{id}" 200 "$(get "$API/results/$id" "$WORK/result.json")"
check T1 "Stored record matches the response" \
  "$(json "$WORK/t1.json" 'd["label"]')" "$(json "$WORK/result.json" 'd["label"]')"
get "$API/images/$id?variant=original" "$WORK/original" >/dev/null
cmp -s "$WORK/original" "$WORK/in/sample.png" && same=yes || same=no
check T1 "Original image is returned byte-for-byte" yes "$same"
check T1 "GET processed 224x224 image" 200 "$(get "$API/images/$id?variant=processed" "$WORK/processed.jpg")"

# T1 again with a JPEG: re-upload the processed image the pipeline just produced.
read -r code secs < <(upload "$WORK/processed.jpg" "processed.jpg")
check T1 "Upload JPEG -> prediction" 200 "$code" "(${secs}s)"

# Validation (T2-T6) and errors (T7).
read -r code secs < <(upload "$WORK/in/too-large.jpg")
check T2 "12 MB upload rejected" 413 "$code" "($(json "$WORK/body" 'd["error"]["code"]'))"
read -r code secs < <(upload "$WORK/in/near-limit.png")
under30="$(python3 -c "print('yes' if float('$secs') < 30 else 'no')")"
check T3 "7.5 MB upload accepted" 200 "$code" "(${secs}s)"
check T3 "...within 30 s" yes "$under30"
read -r code secs < <(upload "$WORK/in/not-an-image.jpg")
check T4 "Text file named .jpg rejected" 415 "$code" "($(json "$WORK/body" 'd["error"]["code"]'))"
read -r code secs < <(upload "$WORK/in/pixel.gif")
check T5 "GIF rejected" 415 "$code"
read -r code secs < <(upload "$WORK/in/vector.svg")
check T5 "SVG rejected" 415 "$code"
read -r code secs < <(upload "$WORK/in/empty.jpg")
check T6 "Empty file rejected" 400 "$code" "($(json "$WORK/body" 'd["error"]["code"]'))"
code="$(curl -s -m 10 -o "$WORK/body" -w '%{http_code}' -F "other=x" "$API/images")"
check T6 "Missing file field rejected" 400 "$code"
check T7 "Unknown imageId" 404 "$(get "$API/results/img_doesnotexist" "$WORK/body")"

# The upload page is served by the gateway.
check UI "GET / serves the upload page" 200 "$(get "$GATEWAY_URL/" "$WORK/index.html")"

echo
echo "$passed passed, $failed failed"
[[ "$failed" -eq 0 ]]
