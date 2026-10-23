#!/usr/bin/env bash
# Build the five KubeVision images.
#
#   scripts/build-images.sh --minikube   build locally, then load into Minikube (local development)
#   scripts/build-images.sh --push       build locally and push to GHCR (for the FABRIC cluster)
#   scripts/build-images.sh              build into the local Docker daemon only
#
# --push needs a one-time `docker login ghcr.io` with a token that has write:packages,
# and the packages set to public so cluster nodes can pull without a secret.
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/angeudybp}"
TAG="${TAG:-0.2.0}"
SERVICES=(gateway preprocess inference metrics-sidecar storage)
SRC="$(cd "$(dirname "$0")/../services-src" && pwd)"

mode="${1:-local}"
case "$mode" in
  --minikube | --push | local) ;;
  *) echo "usage: $0 [--minikube | --push]" >&2; exit 2 ;;
esac

for svc in "${SERVICES[@]}"; do
  image="$REGISTRY/kubevision-$svc:$TAG"
  echo "==> $image"
  docker build -q -t "$image" -f "$SRC/$svc/Dockerfile" "$SRC" >/dev/null
  case "$mode" in
    --push) docker push -q "$image" ;;
    # `minikube image load` works with any Minikube runtime (docker or containerd),
    # unlike `minikube docker-env`, which only supports the docker runtime.
    --minikube) minikube image load --overwrite "$image" ;;
  esac
done

echo "Built ${#SERVICES[@]} images with tag $TAG${mode:+ ($mode)}"
