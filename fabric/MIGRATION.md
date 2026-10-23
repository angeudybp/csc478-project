# Migrating KubeBalancer from Minikube to FABRIC

A step-by-step walkthrough from "it works on Minikube" to "it runs on FABRIC and the evidence is
committed". Do the steps in order; each ends with a **Check** so you know it worked before moving on.
[`README.md`](README.md) in this folder is the reference (file overview, troubleshooting, security).

**Time:** about 1.5 hours the first time, most of it waiting for the slice and the image pushes.

## What changes, and what does not

| | Minikube (now) | FABRIC (target) |
|---|---|---|
| Cluster | 1 node, created by `minikube start` | 3 VMs (`k3s-server`, `k3s-agent-1`, `k3s-agent-2`) running k3s, created by a notebook |
| How images reach the cluster | `scripts/build-images.sh --minikube` loads them directly | Pushed to GHCR; every node pulls them |
| Manifests (`deployments/`, `services/`) | `kubectl apply -f deployments/ -f services/` | **The same files, the same command** |
| Where you run `kubectl` | Your laptop | `k3s-server` (over SSH, or from the notebook) |
| Gateway URL | `minikube service gateway-svc -n imgpipe --url` | SSH tunnel to NodePort 30080, then `http://localhost:30080` |
| Evidence folder | `docs/evidence/m2/minikube/` | `docs/evidence/m2/fabric/` |

Nothing in the services or manifests needs to change.

---

## Step 0. Get FABRIC access (once)

1. Sign in to the [FABRIC portal](https://portal.fabric-testbed.net) with your university account.
2. Ask your instructor to add you to the course's FABRIC **project**. You need project membership to
   create slices.
3. In the portal, create a **bastion key pair** (Experiments → Manage SSH Keys → Bastion) and
   download the private key. FABRIC VMs are only reachable through the bastion host.
4. Open the [FABRIC JupyterHub](https://jupyter.fabric-testbed.net) and run the
   `configure_and_validate.ipynb` notebook from the `jupyter-examples` folder it provides. It
   sets up your project ID, uploads your bastion key, creates a **slice key**, and writes
   `~/work/fabric_config/` (`fabric_rc`, `ssh_config`, `slice_key`, ...).

**Check:** the last cell of `configure_and_validate.ipynb` reports that the configuration is valid.

## Step 1. Pre-flight on your laptop

Make sure what you are about to ship works locally.

```bash
cd ~/Desktop/"CSC 478"/Project
# Unit tests (55)
docker run --rm -v "$PWD/services-src:/src" -w /src python:3.11-slim \
  sh -c "pip install -q -r requirements-dev.txt && pytest -q"
# The stack on Minikube
GATEWAY_URL=<your minikube service URL> scripts/smoke.sh
```

**Check:** `55 passed` and `17 passed, 0 failed`.

## Step 2. Push the code to GitHub

The notebook clones the repository onto `k3s-server`, so it has to be on GitHub, and public.

```bash
git push origin main
```

On GitHub, open the repository → Settings → General → Danger Zone → **Change visibility → Public**
(if it is not already). If it must stay private, see "Private repository" at the end.

**Check:** opening https://github.com/angeudybp/csc478-project in a private browser window shows
`fabric/`, `deployments/` and `services-src/`.

## Step 3. Publish the images to GHCR

FABRIC nodes cannot see your laptop's Docker, so the five images go to the GitHub Container Registry.

1. Create a **classic** personal access token on GitHub (Settings → Developer settings → Personal
   access tokens → Tokens (classic)) with the `write:packages` scope. Copy it.
2. Log in and push. The inference image is about 525 MB, so this takes a while on home upload
   speeds.

   ```bash
   echo "<token>" | docker login ghcr.io -u angeudybp --password-stdin
   scripts/build-images.sh --push
   ```

3. Make each package public: on GitHub, your profile → **Packages** → open
   `kubebalancer-gateway` → Package settings → Danger Zone → **Change visibility → Public**.
   Repeat for `kubebalancer-preprocess`, `kubebalancer-inference`, `kubebalancer-metrics-sidecar`
   and `kubebalancer-storage`.

**Check:** anonymous pulls work.

```bash
docker logout ghcr.io
for s in gateway preprocess inference metrics-sidecar storage; do
  docker manifest inspect ghcr.io/angeudybp/kubebalancer-$s:0.2.0 >/dev/null && echo "$s public" || echo "$s NOT public"
done
```

All five should print `public`.

## Step 4. Put the repository in JupyterHub

In JupyterHub, open a **Terminal** (File → New → Terminal):

```bash
cd ~/work
git clone https://github.com/angeudybp/csc478-project.git
```

**Check:** the file browser shows `work/csc478-project/fabric/create-slice.ipynb`.

## Step 5. Create the cluster (notebook steps 1--3)

Open `work/csc478-project/fabric/create-slice.ipynb`. In the **Settings** cell, leave `SITE = None`
(random site with capacity) or set one, e.g. `SITE = "TACC"`. A site with **IPv4** management
access is the least trouble (the portal's resource map shows sites and their capacity).

Run the cells in order, one at a time:

| Notebook step | What it does | What you should see |
|---|---|---|
| 1. Create the slice | Requests 3 VMs + a private L2 network | A slice table ending in `StableOK` (takes 5--15 min) |
| 2. Configure the network | Assigns 192.168.10.10--12, checks internet access | Three lines ending in `ghcr.io -> HTTP 401`; then three ping lines with `0% packet loss` |
| 3. Install k3s | Server first, then the two agents join it | Install logs, then `kubectl get nodes` showing **3 nodes `Ready`**, each with a `192.168.10.x` INTERNAL-IP |

**Check:** three `Ready` nodes. If `ghcr.io -> HTTP 000` appears in step 2, stop: see the
Troubleshooting table in [`README.md`](README.md) (pick another site, or use `load-images.sh`).

## Step 6. Deploy and smoke-test (notebook step 4)

Run the two cells of step 4. The first clones the repository on `k3s-server` and runs
`kubectl apply -f deployments/ -f services/`; the second runs `scripts/smoke.sh` from inside the cluster.

The first deploy pulls about 900 MB of images on each node, so `rollout status` can take a few
minutes.

**Check:**
- `kubectl -n imgpipe get pods -o wide` shows 7 pods `Running`, inference at `2/2`, and the
  **inference pods spread over more than one NODE**.
- The smoke test ends with `17 passed, 0 failed`.

## Step 7. Reach the gateway from your laptop (notebook step 5)

1. From `~/work/fabric_config/` in JupyterHub, download `ssh_config` and `slice_key` (right-click →
   Download). Put them in `~/fabric_config/` on your laptop together with your bastion private
   key from step 0, then:

   ```bash
   chmod 600 ~/fabric_config/slice_key ~/fabric_config/<bastion key file>
   ```

   Open `~/fabric_config/ssh_config` and change every `IdentityFile` path to the files in
   `~/fabric_config/`.

2. Run the tunnel command the notebook printed in step 5 (adjusting the `-F`/`-i` paths to
   `~/fabric_config/`). It looks like:

   ```bash
   ssh -N -L 30080:192.168.10.10:30080 -F ~/fabric_config/ssh_config -i ~/fabric_config/slice_key ubuntu@<management IP>
   ```

   It prints nothing and keeps running; leave that terminal open.

**Check:**
- http://localhost:30080 in your browser shows the KubeBalancer UI; upload a photo and confirm the
  inference lane shows a pod and that the label is sensible.
- In another terminal on your laptop: `GATEWAY_URL=http://localhost:30080 scripts/smoke.sh` →
  `17 passed, 0 failed`. This shows the external Service working from outside the cluster.

## Step 8. Capture the evidence and screenshots (notebook step 6)

The brief asks for screenshots of `kubectl get deploy,pods,svc`, `kubectl scale`, and a pod
deletion with its recreation. Take them from an SSH session on `k3s-server` (same command as the
tunnel, without `-N -L ...`), **before** running the evidence cell:

```bash
kubectl -n imgpipe get deploy,pods,svc -o wide                                   # screenshot 1
kubectl -n imgpipe scale deploy/inference --replicas=5
kubectl -n imgpipe get pods -l app.kubernetes.io/component=inference -o wide     # screenshot 2
kubectl -n imgpipe scale deploy/inference --replicas=3
kubectl -n imgpipe delete pod <one inference pod> --wait=false
kubectl -n imgpipe get pods -l app.kubernetes.io/component=inference -o wide -w  # screenshot 3, Ctrl-C after the new pod is 2/2
```

Save them as `docs/evidence/m2/screenshots/01-get.png`, `02-scale.png`, `03-self-healing.png`.

Then run the step 6 cell in the notebook. It runs `scripts/evidence.sh fabric` on the server
(about 3 minutes; the last part deletes and recreates the whole stack) and downloads
`evidence-fabric.tgz` into the notebook folder. Your laptop tunnel survives the rebuild because
the NodePort stays 30080.

**Check:** the cell prints `exit=0`, and the tail of the log shows `17 passed, 0 failed`.

## Step 9. Commit the evidence

Download `evidence-fabric.tgz` from JupyterHub to your laptop, then:

```bash
tar xzf ~/Downloads/evidence-fabric.tgz -C docs/evidence/m2/
ls docs/evidence/m2/fabric/        # 00-environment.txt ... 06-rebuild.txt
git add docs/evidence/m2/fabric docs/evidence/m2/screenshots
git commit -m "Add FABRIC evidence for Milestone 2"
git push
```

Then the top-level README's evidence excerpts are switched from Minikube to FABRIC (there is a
`TODO(FABRIC)` marker at that spot); ask Claude to do it from the new files.

**Check:** `docs/evidence/m2/fabric/00-environment.txt` lists three nodes, and
`05-load-balancing.txt` shows requests on all three inference replicas.

## Step 10. Clean up

When you no longer need the cluster, run the last notebook cell with `slice.delete()` uncommented.
Slices expire automatically (about a day by default; extend them in the portal if you need longer
for the demo), and the notebook recreates everything from scratch in about 20 minutes.

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
# on k3s-server:
cd kubebalancer && git pull && kubectl apply -f deployments/
```

`kubectl apply` sees the changed image and rolls the pods one by one, without downtime.

## Private repository

If the repository cannot be public, skip `git clone` on the server and upload your JupyterHub
copy instead. Replace the first line of notebook step 4 with:

```python
server.upload_directory("..", "kubebalancer")
```

(JupyterHub needs the code anyway, which you cloned in step 4 with your GitHub credentials.)
