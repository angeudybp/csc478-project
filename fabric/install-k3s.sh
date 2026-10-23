#!/usr/bin/env bash
# Install k3s on one FABRIC VM, bound to the slice's private network.
#
#   sudo ./install-k3s.sh server <node-ip> <token-file>
#   sudo ./install-k3s.sh agent  <node-ip> <token-file> <server-ip>
#
# <node-ip> is this VM's address on the slice's L2 network (e.g. 192.168.10.10). k3s is told to
# use that interface for node traffic and for flannel, so pod-to-pod traffic stays on the
# private network rather than the management NIC. Traefik is disabled: the gateway is exposed
# with a NodePort Service, so no ingress controller is needed.
#
# The join token is read from <token-file>, never from the command line (which would show up in
# `ps` and in sudo's auth log). It is moved to a root-only file that k3s reads on every start.
# Agents should be given the server's /var/lib/rancher/k3s/server/node-token: it embeds the
# cluster CA hash, so the agent verifies it is joining the real server.
set -euo pipefail

K3S_VERSION="v1.31.4+k3s1"
# install.sh from the same k3s tag, pinned by checksum. It verifies the k3s binary it downloads
# against the release's sha256sum file. To upgrade: change both values together.
INSTALLER_URL="https://raw.githubusercontent.com/k3s-io/k3s/$K3S_VERSION/install.sh"
INSTALLER_SHA256="f60c3d8940dfc896f7d83aaf57726c91cf21afc4bca40036472df108d9700b4b"
TOKEN_PATH=/etc/rancher/k3s-join-token

usage() {
  echo "usage: $0 server <node-ip> <token-file> | agent <node-ip> <token-file> <server-ip>" >&2
  exit 2
}

[[ $# -ge 3 ]] || usage
role="$1"
node_ip="$2"
token_file="$3"
server_ip="${4:-}"
[[ "$role" == server || "$role" == agent ]] || usage
[[ "$role" == server || -n "$server_ip" ]] || usage
[[ "$EUID" -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
[[ -s "$token_file" ]] || { echo "token file $token_file is missing or empty" >&2; exit 1; }

# The interface that carries <node-ip>, e.g. enp7s0.
iface="$(ip -o -4 addr show | awk -v ip="$node_ip" '{ split($4, a, "/"); if (a[1] == ip) print $2 }')"
if [[ -z "$iface" ]]; then
  echo "No interface has address $node_ip; configure the slice network first." >&2
  exit 1
fi
echo "Installing k3s $K3S_VERSION as $role on $iface ($node_ip)"

install -d -m 755 /etc/rancher
install -m 600 -o root -g root "$token_file" "$TOKEN_PATH"
rm -f "$token_file"

installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT
curl -fsSL "$INSTALLER_URL" -o "$installer"
echo "$INSTALLER_SHA256  $installer" | sha256sum -c --quiet - || {
  echo "install.sh checksum mismatch; refusing to run it" >&2
  exit 1
}

common=(--node-ip "$node_ip" --flannel-iface "$iface")
export INSTALL_K3S_VERSION="$K3S_VERSION" K3S_TOKEN_FILE="$TOKEN_PATH"

if [[ "$role" == server ]]; then
  sh "$installer" server "${common[@]}" \
    --advertise-address "$node_ip" --tls-san "$node_ip" --disable traefik
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
else
  K3S_URL="https://$server_ip:6443" sh "$installer" agent "${common[@]}"
fi
