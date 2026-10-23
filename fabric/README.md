# Deploying KubeVision on FABRIC

**First time? Follow [`MIGRATION.md`](MIGRATION.md)**, a step-by-step walkthrough from Minikube to
submitted FABRIC evidence. This page is the reference.

The submitted deployment runs on a 3-node [RKE2](https://docs.rke2.io) cluster in a FABRIC slice,
built with the same Ansible playbooks as the course's FABRIC labs. The manifests in `deployments/`
and `services/` are the same ones used on Minikube; only the way images reach the nodes and the way
you reach the gateway differ.

```
 laptop ── localhost:3000 ──► course container ──ssh tunnel──► bastion ──► node1 (RKE2 server) ─┐
 (browser, smoke.sh)         (JupyterLab, Ansible)                         192.168.1.1          │ private L2 network
                                                                           node2 (agent) ───────┤ 192.168.1.0/24
                                                                           192.168.1.2          │ (node and pod traffic,
                                                                           node3 (agent) ───────┘  NFS share /opt/data)
                                                                           192.168.1.3
```

| File | What it does |
|---|---|
| `MIGRATION.md` | Step-by-step migration from Minikube to FABRIC, with a check after each step |
| `kubevision.ipynb` | The runbook: creates the slice, installs RKE2, deploys, runs smoke and evidence, opens the UI tunnel |
| `templates/` | Ansible templates for the inventory and the prerequisites/RKE2 playbooks, copied unchanged from the course (`csc478/09_resource_observation/templates/`) |
| `playbook/playbook-nfs.yml` | The course's NFS playbook: node1 exports `/opt/data` to the other nodes (for the Milestone 3 volume) |
| `load-images.sh` | Fallback: copies images from your laptop into each node when they cannot pull from GHCR |

## Where the runbook runs

The runbook needs the course's local FABRIC environment (the `fabric` repository with
`docker-compose.yml`, `utils/ansible.py`, your FABRIC token and keys). It lives there in
`fabric/project/`, which `docker-compose.yml` mounts at `/home/fabric/project`:

```yaml
    volumes:
      # ...the course's mounts...
      - ./project:/home/fabric/project
```

This folder keeps a copy so the deployment is reproducible from the repository. To set it up from
scratch, copy `kubevision.ipynb`, `templates/` and `playbook/` into `<course repo>/project/`.

## 1. Publish the images to GHCR (once per image change)

The nodes pull `ghcr.io/angeudybp/kubevision-<service>:0.2.0`.

```bash
docker login ghcr.io -u angeudybp      # password: a classic token with write:packages
scripts/build-images.sh --push
```

Then, on GitHub, open each of the five `kubevision-*` packages (Profile → Packages → package →
Package settings) and set **visibility to Public**. The cluster then needs no pull secret.

Pushed tags are reused as-is: if you change a service, bump `TAG` (in `build-images.sh` and the
manifests), because `imagePullPolicy: IfNotPresent` keeps the copy a node already has.

## 2. Run the runbook

Start the environment (`docker compose up -d` in the course repository), open
http://localhost:8888/lab/tree/project/kubevision.ipynb and run the cells in order:

1. **Create the slice:** three Ubuntu 22.04 VMs (4 cores, 8 GB, 40 GB) at the first site with
   capacity, on an L2 network with `192.168.1.1–3`.
2. **Install RKE2:** generates the inventory from the live slice and runs the course's prerequisites,
   NFS and RKE2 playbooks (logs in `logs/`), then removes the playbook's `nginx-demo`, which holds
   NodePort 30080.
3. **Registry check:** every node should report `ghcr.io -> HTTP 401`.
4. **Deploy:** clones this repository on node1, `kubectl apply -f deployments/ -f services/`, then
   `scripts/smoke.sh` against `http://192.168.1.1:30080`.
5. **UI tunnel:** an SSH tunnel from the container to the NodePort, on the container's published
   port 3000.
6. **Screenshots:** prints node1's SSH command and the `kubectl` commands to capture.
7. **Evidence:** `scripts/evidence.sh fabric` on node1; the output is unpacked into `evidence/fabric/`.
8. **Delete the slice.**

## 3. Reach the gateway from your laptop

With the tunnel cell running, on your laptop:

- open **http://localhost:3000** for the upload UI;
- run `GATEWAY_URL=http://localhost:3000 scripts/smoke.sh`.

`30080` is the fixed NodePort of `gateway-svc`, and any node's `192.168.1.x` address works as the
tunnel target, since kube-proxy routes the NodePort to the gateway pod wherever it runs.

## Security notes

- **The cluster join token is random**, generated once per runbook folder and kept in
  `playbook/rke2-token` (mode 600, git-ignored), instead of the course helper's fixed default. The
  generated `playbook/inventory.yml` contains it too and is also mode 600 and git-ignored.
- **The kubeconfig** (cluster-admin credentials) stays on node1 at mode 600.
- **Port 3000 is published on all of your machine's interfaces** by the course's
  `docker-compose.yml`, so while the tunnel runs, other devices on your network can reach the UI.
  Close the tunnel (`tunnel.terminate()`) when you are not using it.
- **The NFS share** (`/opt/data`, from the course playbook) is world-writable and exported to the
  private `192.168.1.0/24` network only, which nothing outside the slice can reach.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| A playbook fails | The cell prints the last 30 lines of its log; the full log is in `logs/<site>-ansible-<name>.log`. Rerunning the cell is safe (the playbooks are idempotent and the token is reused). |
| `ghcr.io -> HTTP 000` in step 3 | That node cannot reach GHCR. Run `load-images.sh` from your laptop for each node, or delete the slice and rerun step 1 with that site removed from `sites`. |
| Pods stuck in `ImagePullBackOff` | Packages not public, wrong tag, or no registry access. `kubectl -n imgpipe describe pod <pod>` shows which. |
| Nodes stay `NotReady` | The Canal network did not come up on the dataplane. See the end of `logs/<site>-ansible-rke2.log`; the course playbook pins Canal to the interface that reaches `192.168.1.254`. |
| Tunnel cell: `exited with code 255` | Port 3000 is taken in the container, or SSH could not reach node1. Close an old tunnel with `tunnel.terminate()` and rerun. |
| Private addresses gone after a VM reboot | `ip_addr_add` is not persistent. Rerun the networking part of step 1 for that node. |
