#!/usr/bin/env bash
# Fallback for when FABRIC nodes cannot pull from ghcr.io: copy the images from this machine's
# Docker straight into each node's containerd. The manifests use imagePullPolicy: IfNotPresent,
# so Kubernetes then uses the imported copy and never contacts the registry.
#
#   scripts/build-images.sh            # build the images locally first
#   SSH_CONFIG=~/fabric_config/ssh_config fabric/load-images.sh ubuntu@<mgmt-ip> [ubuntu@<mgmt-ip> ...]
#
# Every node needs the images: any of them may run any pod. SSH_CONFIG is the FABRIC ssh_config
# that routes through the bastion host (see fabric/README.md).
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/angeudybp}"
TAG="${TAG:-0.2.0}"
SERVICES=(gateway preprocess inference metrics-sidecar storage)
# RKE2's bundled containerd client and socket.
CTR="sudo /var/lib/rancher/rke2/bin/ctr --address /run/k3s/containerd/containerd.sock -n k8s.io"

[[ $# -ge 1 ]] || { echo "usage: $0 <ssh-target> [<ssh-target> ...]" >&2; exit 2; }
ssh_opts=()
[[ -n "${SSH_CONFIG:-}" ]] && ssh_opts=(-F "$SSH_CONFIG")

images=()
for svc in "${SERVICES[@]}"; do images+=("$REGISTRY/kubevision-$svc:$TAG"); done

# $CTR is meant to expand here, on this machine, into the command the node runs.
# shellcheck disable=SC2029
for target in "$@"; do
  echo "==> $target"
  # One stream for all images, so shared base layers are sent once per node.
  docker save "${images[@]}" | gzip -1 | ssh "${ssh_opts[@]}" "$target" "gunzip | $CTR images import -"
  ssh "${ssh_opts[@]}" "$target" "$CTR images ls -q | grep kubevision"
done
