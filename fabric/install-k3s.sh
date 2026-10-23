#!/usr/bin/env bash
# Install k3s on one FABRIC VM, bound to the slice's private network.
#
#   sudo ./install-k3s.sh server <node-ip> <token>
#   sudo ./install-k3s.sh agent  <node-ip> <token> <server-ip>
#
# <node-ip> is this VM's address on the slice's L2 network (e.g. 192.168.10.10). k3s is told to
# use that interface for node traffic and for flannel, so pod-to-pod traffic stays on the
# private network rather than the management NIC. Traefik is disabled: the gateway is exposed
# with a NodePort Service, so no ingress controller is needed.
set -euo pipefail

K3S_VERSION="${K3S_VERSION:-v1.31.4+k3s1}"

usage() {
  echo "usage: $0 server <node-ip> <token> | agent <node-ip> <token> <server-ip>" >&2
  exit 2
}

[[ $# -ge 3 ]] || usage
role="$1"
node_ip="$2"
token="$3"
server_ip="${4:-}"
[[ "$EUID" -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }

# The interface that carries <node-ip>, e.g. enp7s0.
iface="$(ip -o -4 addr show | awk -v ip="$node_ip" '{ split($4, a, "/"); if (a[1] == ip) print $2 }')"
if [[ -z "$iface" ]]; then
  echo "No interface has address $node_ip; configure the slice network first." >&2
  exit 1
fi
echo "Installing k3s $K3S_VERSION as $role on $iface ($node_ip)"

common=(--node-ip "$node_ip" --flannel-iface "$iface")
installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT
curl -sfL https://get.k3s.io -o "$installer"

case "$role" in
  server)
    INSTALL_K3S_VERSION="$K3S_VERSION" K3S_TOKEN="$token" sh "$installer" server "${common[@]}" \
      --advertise-address "$node_ip" --tls-san "$node_ip" \
      --disable traefik
    # Wait for the API server, so agents can join as soon as this returns.
    for _ in $(seq 60); do
      kubectl get nodes >/dev/null 2>&1 && break
      sleep 2
    done
    kubectl get nodes -o wide
    # The kubeconfig holds cluster-admin credentials, so k3s keeps it at mode 0600. Give the login
    # user (who ran sudo) a private copy so kubectl works without sudo.
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
      home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
      install -d -m 700 -o "$SUDO_USER" -g "$SUDO_USER" "$home/.kube"
      install -m 600 -o "$SUDO_USER" -g "$SUDO_USER" /etc/rancher/k3s/k3s.yaml "$home/.kube/config"
    fi
    ;;
  agent)
    [[ -n "$server_ip" ]] || usage
    INSTALL_K3S_VERSION="$K3S_VERSION" K3S_URL="https://$server_ip:6443" K3S_TOKEN="$token" \
      sh "$installer" agent "${common[@]}"
    ;;
  *)
    usage
    ;;
esac
