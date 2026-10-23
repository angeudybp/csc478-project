# Deploying KubeBalancer on FABRIC

The submitted deployment runs on a 3-node [k3s](https://k3s.io) cluster in a FABRIC slice. The
manifests in `deployments/` and `services/` are the same ones used on Minikube; only the way images
reach the nodes and the way you reach the gateway differ.

```
 laptop ──ssh tunnel──► bastion ──► k3s-server ─┐
 (browser, smoke.sh)                192.168.10.10│  private L2 network 192.168.10.0/24
                                    k3s-agent-1 ─┤  (node traffic and pod network)
                                    192.168.10.11│
                                    k3s-agent-2 ─┘
                                    192.168.10.12
```

| File | What it does |
|---|---|
| `create-slice.ipynb` | Creates the slice, installs k3s, deploys, runs smoke and evidence (FABRIC JupyterHub) |
| `install-k3s.sh` | Installs k3s on one VM as server or agent, bound to the private network |
| `load-images.sh` | Fallback: copies images from your laptop into each node when they cannot pull from GHCR |

## 1. Prerequisites

- A FABRIC account in a project with VM and L2 network permissions, and access to the
  [FABRIC JupyterHub](https://jupyter.fabric-testbed.net).
- Your **bastion key** and **slice key** set up in JupyterHub (the `configure_and_validate`
  notebook in `jupyter-examples` does this). It also writes `fabric_config/ssh_config`, which
  you need for SSH from your laptop: download that file, `fabric_bastion_key` and `slice_key`
  to your laptop (e.g. `~/fabric_config/`) and fix the key paths inside `ssh_config`.

## 2. Publish the images to GHCR (once per image change)

The nodes pull `ghcr.io/angeudybp/kubebalancer-<service>:0.2.0`.

```bash
# A GitHub personal access token (classic) with the write:packages scope:
echo "$GHCR_TOKEN" | docker login ghcr.io -u angeudybp --password-stdin
scripts/build-images.sh --push
```

Then, on GitHub, open each of the five `kubebalancer-*` packages (Profile → Packages → package →
Package settings) and set **visibility to Public**. The cluster then needs no pull secret.

Pushed tags are reused as-is: if you change a service, either bump `TAG` (in `build-images.sh`
and the manifests) or delete the old image on the nodes, because `imagePullPolicy: IfNotPresent`
keeps the copy a node already has.

## 3. Create the cluster and deploy

In FABRIC JupyterHub, clone this repository, open `fabric/create-slice.ipynb`, and run the cells
in order. The notebook:

1. creates three Ubuntu 24.04 VMs (4 cores, 8 GB, 20 GB disk) at one site, joined by an L2 network;
2. assigns `192.168.10.10–12` and checks each VM can reach `ghcr.io`
   (on sites with IPv6-only management it first switches DNS to public NAT64 resolvers);
3. installs k3s (server first) and waits for all three nodes to be `Ready`;
4. clones the repository on `k3s-server`, applies the manifests, and runs `scripts/smoke.sh`.

The repository must be **public** for step 4's `git clone`. If it is private, upload it instead:
`server.upload_directory("..", "kubebalancer")` from the notebook.

## 4. Reach the gateway from your laptop

The notebook prints a command like this (bastion details come from your `ssh_config`):

```bash
ssh -N -L 30080:192.168.10.10:30080 -F ~/fabric_config/ssh_config -i ~/fabric_config/slice_key ubuntu@<k3s-server management IP>
```

Leave it running, then:

- open **http://localhost:30080** for the upload UI;
- run `GATEWAY_URL=http://localhost:30080 scripts/smoke.sh`.

`30080` is the fixed NodePort of `gateway-svc`. Any node's `192.168.10.x` address works as the
tunnel target, since kube-proxy routes the NodePort to the gateway pod wherever it runs.

## 5. Capture the evidence

The last notebook cells run `scripts/evidence.sh fabric` **on `k3s-server`** (it has `kubectl`,
`curl` and `python3`) and download `evidence-fabric.tgz`. Unpack it into `docs/evidence/m2/` and
commit. Take terminal screenshots while it runs (or rerun individual commands in an SSH session
on the server) for the README.

To run it from an SSH session instead:

```bash
cd kubebalancer && GATEWAY_URL=http://192.168.10.10:30080 scripts/evidence.sh fabric
```

## 6. Clean up

Run the `slice.delete()` cell. Slices also expire on their own (renew in the portal if you
need longer); everything needed to recreate the cluster is in the notebook.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `ghcr.io -> HTTP 000` in step 2 | The VM has no route to GHCR (IPv6-only site where NAT64 did not help). Pick another site, or after step 3 run `fabric/load-images.sh` from your laptop for each node. |
| Pods stuck in `ImagePullBackOff` | Packages not public, wrong tag, or no registry access. `kubectl -n imgpipe describe pod <pod>` shows which; fix visibility or use `load-images.sh`. |
| Agents never become `Ready` | They cannot reach `192.168.10.10:6443`. Check the ping cell in step 2 and that the private interface is up (`ip -4 addr`). |
| All inference pods on one node | Fine, but unexpected: the spread constraint is soft. Check `kubectl get nodes` shows three `Ready` nodes before deploying. |
| Private addresses gone after a VM reboot | `ip_addr_add` is not persistent. Rerun the step 2 cell. |
