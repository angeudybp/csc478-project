# Migrating KubeVision from Minikube to FABRIC

A step-by-step walkthrough from "it works on Minikube" to "it runs on FABRIC and the evidence is
committed". Do the steps in order; each ends with a **Check** so you know it worked before moving on.
[`README.md`](README.md) in this folder is the reference (file overview, troubleshooting, security).

**Time:** about an hour, most of it waiting for the slice and the RKE2 install.

## What changes, and what does not

| | Minikube (development) | FABRIC (submitted) |
|---|---|---|
| Cluster | 1 node, created by `minikube start` | 3 VMs running RKE2 (`node1` server, `node2`–`node3` agents), created by the runbook with the course's Ansible playbooks |
| How images reach the cluster | `scripts/build-images.sh --minikube` loads them directly | Pulled by every node from public GHCR packages |
| Manifests (`deployments/`, `services/`) | `kubectl apply -f deployments/ -f services/` | **The same files, the same command** |
| Where you run `kubectl` | Your laptop | `node1` (from the runbook, or a JupyterLab terminal) |
| Gateway URL | `minikube service gateway-svc -n imgpipe --url` | `http://localhost:3000`, through the runbook's SSH tunnel |
| Evidence folder | `docs/evidence/m2/minikube/` | `docs/evidence/m2/fabric/` |

Nothing in the services or manifests needs to change.

---

## Step 0. The course's FABRIC environment (once)

You need the course's local JupyterLab environment set up as its `Readme.md` describes:
`home/fabric/.fabric/fabric_rc` with your project ID and bastion username, a current
`id_token.json`, and the bastion and slice key pairs.

**Check:** a course notebook (for example `csc478/09_resource_observation/rke2.ipynb`) gets through
its `fablib.verify_and_configure()` cell without errors.

## Step 1. Pre-flight on your laptop

Make sure what you are about to ship works locally.

```bash
cd ~/Desktop/"CSC 478"/Project
# Unit tests (57)
docker run --rm -v "$PWD/services-src:/src" -w /src python:3.11-slim \
  sh -c "pip install -q -r requirements-dev.txt && pytest -q"
# The stack on Minikube
GATEWAY_URL=<your minikube service URL> scripts/smoke.sh
```

**Check:** `57 passed` and `18 passed, 0 failed`.

## Step 2. Push the code and the images

node1 clones the repository, and every node pulls the images, so both must be on GitHub and public.

```bash
git push origin main
docker login ghcr.io -u angeudybp        # password: a classic token with write:packages
scripts/build-images.sh --push
```

Make each of the five packages public: your GitHub profile → **Packages** → `kubevision-<service>`
→ Package settings → Danger Zone → **Change visibility → Public**.

**Check:** anonymous pulls work. With an empty Docker config, so your login is not used:

```bash
mkdir -p /tmp/anon && echo '{}' > /tmp/anon/config.json
for s in gateway preprocess inference metrics-sidecar storage; do
  DOCKER_CONFIG=/tmp/anon docker manifest inspect ghcr.io/angeudybp/kubevision-$s:0.2.0 >/dev/null \
    && echo "$s public" || echo "$s NOT public"
done
```

All five should print `public`.

## Step 3. Put the runbook in the course environment

In the course repository (`~/Desktop/CSC 478/fabric`):

1. Copy this folder's `kubevision.ipynb`, `templates/` and `playbook/` into `project/`.
2. Add the mount to `docker-compose.yml`, under `volumes:`:

   ```yaml
         - ./project:/home/fabric/project
   ```

3. Start (or recreate) the container: `docker compose up -d`.

**Check:** http://localhost:8888/lab/tree/project/kubevision.ipynb opens the runbook.

## Step 4. Create the cluster (runbook steps 1–3)

Run the cells in order, one at a time:

| Runbook step | What it does | What you should see |
|---|---|---|
| Settings and imports | Loads fablib and the course's `utils/ansible.py` | No errors |
| 1. Create the slice | Requests 3 VMs + a private L2 network at the first site with capacity | `node1 -> 192.168.1.1` (and 2, 3), then `Slice at <SITE> is stable: True` (5–15 min) |
| 2. Install RKE2 | Prerequisites, NFS and RKE2 playbooks | `prereqs`, `nfs` and `rke2 playbook is completed` (10–15 min) |
| (validation) | `kubectl get nodes`, nginx-demo check, demo removed | **3 nodes `Ready`**, `RKE2 works` |
| 3. Registry check | `curl https://ghcr.io/v2/` from each node | Three lines ending in `ghcr.io -> HTTP 401` |

**Check:** three `Ready` nodes and three `HTTP 401` lines. For anything else, see Troubleshooting in
[`README.md`](README.md).

## Step 5. Deploy and smoke-test (runbook step 4)

The first cell clones the repository on node1 and applies the manifests; the second runs the smoke
test from node1. The first deploy pulls about 1.4 GB of images on each node, so `rollout status` can
take a few minutes.

**Check:**
- `kubectl -n imgpipe get deploy,pods,svc -o wide` shows 7 pods `Running`, inference at `2/2`, and
  the **inference pods spread over more than one NODE**.
- The smoke test ends with `18 passed, 0 failed`.

## Step 6. Open the UI from your laptop (runbook step 5)

Run the tunnel cell. It prints `Tunnel is up`.

**Check:**
- http://localhost:3000 shows the KubeVision UI; upload a photo and confirm the label is sensible
  and the pipeline strip names an inference pod.
- From the repository on your laptop: `GATEWAY_URL=http://localhost:3000 scripts/smoke.sh` →
  `18 passed, 0 failed`. This shows the external Service working from outside the cluster.

## Step 7. Screenshots, then the evidence (runbook steps 6 and 7)

Take the screenshots **before** running the evidence cell, which deletes and recreates the stack.
Print node1's SSH command with the cell in runbook step 6, open a **Terminal** in JupyterLab
(File → New → Terminal), paste it, and capture:

```bash
kubectl -n imgpipe get deploy,pods,svc -o wide                                   # 01-get.png
kubectl -n imgpipe scale deploy/inference --replicas=5
kubectl -n imgpipe get pods -l app.kubernetes.io/component=inference -o wide     # 02-scale.png
kubectl -n imgpipe scale deploy/inference --replicas=3
kubectl -n imgpipe delete pod <one inference pod> --wait=false
kubectl -n imgpipe get pods -l app.kubernetes.io/component=inference -o wide -w  # 03-self-healing.png (Ctrl-C once the new pod is 2/2)
```

Also capture the UI with a classified image (`04-ui.png`).

Then run the evidence cell. It runs `scripts/evidence.sh fabric` on node1 (about 5 minutes) and
unpacks the output into `project/evidence/fabric/` in the course repository. The UI tunnel survives
the rebuild because the NodePort stays 30080.

**Check:** the cell prints `exit=0`, the log tail shows `18 passed, 0 failed`, and it lists
`00-environment.txt` … `06-rebuild.txt`.

## Step 8. Commit the evidence

```bash
cd ~/Desktop/"CSC 478"/Project
cp -r ../fabric/project/evidence/fabric docs/evidence/m2/
mkdir -p docs/evidence/m2/screenshots && cp <your screenshots> docs/evidence/m2/screenshots/
git add docs/evidence/m2/fabric docs/evidence/m2/screenshots
git commit -m "Add FABRIC evidence for Milestone 2"
git push
```

Then switch the top-level README's evidence excerpts from Minikube to FABRIC (there is a
`TODO(FABRIC)` marker at that spot).

**Check:** `docs/evidence/m2/fabric/00-environment.txt` lists three nodes, and
`05-load-balancing.txt` shows requests on all three inference replicas.

## Step 9. Clean up

Close the tunnel and delete the slice with the last runbook cell. Slices also expire on their own
(extend them in the portal if you need longer for the demo), and the runbook recreates everything
in about 30 minutes.

---

## Changing code after the migration

Nodes keep an image once they have it (`imagePullPolicy: IfNotPresent`), so pushing a new image
under the **same tag** does nothing on FABRIC. Use a new tag for every change you deploy:

```bash
NEW=0.2.1
sed -i "s/:0\.2\.0/:$NEW/" deployments/*.yaml
sed -i "s/TAG:-0\.2\.0/TAG:-$NEW/" scripts/build-images.sh
scripts/build-images.sh --push           # then make any *new* package public
git commit -am "Release $NEW" && git push
# on node1:
cd kubevision && git pull && kubectl apply -f deployments/
```

`kubectl apply` sees the changed image and rolls the pods one by one, without downtime.
