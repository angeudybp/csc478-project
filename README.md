# KubeBalancer --- Image Classification Pipeline on Kubernetes

CSC 478 (Cloud Engineering) course project. A four-service image classification pipeline on
Kubernetes: upload an image to one public endpoint, get back a predicted label from MobileNetV2,
and retrieve the original image, the processed image, and the prediction afterwards by ID.
It is deployed on a 3-node k3s cluster on [FABRIC](https://portal.fabric-testbed.net) and
developed locally on Minikube.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M1 --- Architecture** | Design only: components, Services, API contracts, persistence plan, risk and test plan | **Complete** --- see [`docs/report/Milestone1-Report.pdf`](docs/report/Milestone1-Report.pdf) |
| **M2 --- Core implementation** | Deployments, Services, sidecar, scaling and self-healing. No persistence | **Complete on Minikube**; FABRIC run pending (see [Evidence](#evidence-of-scaling-and-self-healing)) |
| M3 --- Persistence and demo | PV/PVC, resource limits, image downloads in the UI, demo video, final report | Not started |

## Architecture at a glance

Four Deployments in the `imgpipe` namespace, wired together by Service DNS names:

| Deployment | Replicas | Containers | Service | Role |
|---|---|---|---|---|
| `gateway` | 1 | gateway | `gateway-svc` **NodePort 30080** | The only external entrypoint. Validates uploads (8 MB, JPEG/PNG), calls the other services in order, serves the web UI and the retrieval API |
| `preprocess` | 2 | preprocess | `preprocess-svc` ClusterIP 8081 | Strips metadata, crops and resizes to 224×224 |
| `inference` | **3** | inference + **metrics-exporter sidecar** | `inference-svc` ClusterIP 8082, 9100 | MobileNetV2 (ImageNet-1k) on ONNX Runtime |
| `storage` | 1 | storage | `storage-svc` ClusterIP 8083 | Saves the original, the 224 px image and the prediction. `emptyDir` in M2; a PVC in M3 |

An upload flows **gateway → preprocess → inference → storage**, and the response carries the label,
the top 3 classes, per-hop timings, and which inference replica served it. Every container has
liveness (`/healthz`) and readiness (`/readyz`) probes; inference is ready only after the model has
loaded.

## Repository layout

```
deployments/         Namespace and the four Deployments (00-namespace.yaml, 10-13-*.yaml)
services/            The four Services (20-23-*-svc.yaml)
services-src/        Source and Dockerfile for each service; gateway/ui/ is the React web UI
scripts/             build-images.sh, smoke.sh (API tests), evidence.sh (operational evidence)
fabric/              FABRIC deployment: slice notebook, k3s install, image fallback (see fabric/README.md)
docs/evidence/m2/    Captured command output, per cluster (minikube/, fabric/)
docs/report/         Milestone reports: Word source (.docx) and submitted PDF
docs/diagrams/       Mermaid diagram sources (.mmd) and rendered diagrams in out/
```

## Deploy

The manifests are the same on every cluster; they are numbered so one command creates the
namespace first:

```bash
kubectl apply -f deployments/ -f services/
kubectl -n imgpipe get deploy,pods,svc
```

Tear down and rebuild with no manual steps (test T12):

```bash
kubectl delete -f deployments/ -f services/
kubectl apply  -f deployments/ -f services/
```

The images must be available to the cluster first.

### On FABRIC (the submitted deployment)

Publish the images to GHCR (`scripts/build-images.sh --push`, then make the packages public), then
run [`fabric/create-slice.ipynb`](fabric/create-slice.ipynb) in FABRIC JupyterHub. It creates three
VMs on a private network, installs k3s (one server, two agents), runs the `kubectl apply` above,
and runs the smoke test. Step-by-step walkthrough: [`fabric/MIGRATION.md`](fabric/MIGRATION.md);
reference and troubleshooting: [`fabric/README.md`](fabric/README.md).

### On Minikube (local development)

```bash
minikube start --driver=docker
scripts/build-images.sh --minikube        # builds the five images and loads them into Minikube
kubectl apply -f deployments/ -f services/
kubectl -n imgpipe rollout status deploy/inference
```

## Access the external Service

`gateway-svc` is a **NodePort** Service on port **30080**: the only way into the cluster. Neither
Minikube nor a bare k3s cluster has a cloud load balancer, so a `LoadBalancer` Service would stay
`Pending`. The other three Services are ClusterIP and unreachable from outside.

| Cluster | Gateway URL |
|---|---|
| FABRIC | Open an SSH tunnel through the bastion: `ssh -N -L 30080:192.168.10.10:30080 -F ~/fabric_config/ssh_config ubuntu@<k3s-server management IP>` (the notebook prints the exact command), then use **http://localhost:30080** |
| Minikube (VM driver, or Docker driver with a routable node IP) | `http://$(minikube ip):30080` |
| Minikube with Docker Desktop | `minikube service gateway-svc -n imgpipe --url` and keep that terminal open; use the URL it prints |

Open the gateway URL in a browser for the upload UI. It shows the prediction, the original next to
the 224×224 image the model saw, the route the request took (with per-hop timings and the inference
replica that served it), and recent uploads. Or use the API:

```bash
curl -F "file=@dog.jpg" http://localhost:30080/api/v1/images       # classify
curl http://localhost:30080/api/v1/results/<imageId>                # fetch a stored result
curl -o out.jpg "http://localhost:30080/api/v1/images/<imageId>?variant=processed"
```

Run the API test suite (the M2 cases from the M1 test matrix) against any cluster:

```bash
GATEWAY_URL=http://localhost:30080 scripts/smoke.sh      # 17 checks
```

## Evidence of scaling and self-healing

`scripts/evidence.sh <cluster>` runs every check below and saves each command with its output to
`docs/evidence/m2/<cluster>/`. The excerpts here are from **Minikube**
([`docs/evidence/m2/minikube/`](docs/evidence/m2/minikube/)); the FABRIC run goes to
`docs/evidence/m2/fabric/` and replaces them for submission.

<!-- TODO(FABRIC): replace the excerpts below with docs/evidence/m2/fabric/ output and add screenshots
     to docs/evidence/m2/screenshots/ (kubectl get, kubectl scale, pod delete + recreate). -->

**Everything deployed** ([`01-overview.txt`](docs/evidence/m2/minikube/01-overview.txt)): four
Deployments, inference at 3/3 with two containers per pod, one NodePort and three ClusterIP Services.

```
$ kubectl -n imgpipe get deploy,pods,svc
NAME                         READY   UP-TO-DATE   AVAILABLE   CONTAINERS
deployment.apps/gateway      1/1     1            1           gateway
deployment.apps/inference    3/3     3            3           inference,metrics-exporter
deployment.apps/preprocess   2/2     2            2           preprocess
deployment.apps/storage      1/1     1            1           storage

NAME                             READY   STATUS    RESTARTS   AGE
pod/gateway-b85554b77-6qss7      1/1     Running   0          3m32s
pod/inference-65d9f64cb7-fsrln   2/2     Running   0          3m32s
pod/inference-65d9f64cb7-m898h   2/2     Running   0          3m31s
pod/inference-65d9f64cb7-zzzbv   2/2     Running   0          3m29s
pod/preprocess-884ff4686-drsxn   1/1     Running   0          44m
pod/preprocess-884ff4686-fdsdv   1/1     Running   0          44m
pod/storage-7755f68d4b-5jbgg     1/1     Running   0          44m

NAME                     TYPE        CLUSTER-IP       PORT(S)
service/gateway-svc      NodePort    10.103.101.90    8080:30080/TCP
service/inference-svc    ClusterIP   10.105.194.221   8082/TCP,9100/TCP
service/preprocess-svc   ClusterIP   10.108.46.98     8081/TCP
service/storage-svc      ClusterIP   10.103.96.118    8083/TCP
```

**Scaling** ([`02-scaling.txt`](docs/evidence/m2/minikube/02-scaling.txt)): inference scaled from
3 to 1 and back to 3.

```
$ kubectl -n imgpipe scale deploy/inference --replicas=1
$ kubectl -n imgpipe get deploy/inference
NAME        READY   UP-TO-DATE   AVAILABLE
inference   1/1     1            1

$ kubectl -n imgpipe scale deploy/inference --replicas=3
$ kubectl -n imgpipe get deploy/inference
NAME        READY   UP-TO-DATE   AVAILABLE
inference   3/3     3            3
```

**Self-healing** ([`03-self-healing.txt`](docs/evidence/m2/minikube/03-self-healing.txt)): one
inference pod deleted while uploads ran every 0.25 s. The ReplicaSet created `vxts5` immediately
and it was `2/2 Running` within 2 s; **all 73 uploads during the deletion returned 200**.

```
$ kubectl -n imgpipe delete pod inference-65d9f64cb7-gxtl5
$ kubectl -n imgpipe get pods -l app.kubernetes.io/component=inference --watch
NAME                         READY   STATUS              RESTARTS   AGE
inference-65d9f64cb7-gxtl5   2/2     Terminating         0          8s
inference-65d9f64cb7-lngzv   2/2     Running             0          8s
inference-65d9f64cb7-vxts5   0/2     ContainerCreating   0          0s
inference-65d9f64cb7-zzzbv   2/2     Running             0          3m38s
inference-65d9f64cb7-vxts5   1/2     Running             0          2s
inference-65d9f64cb7-vxts5   2/2     Running             0          2s
```

**Also captured:**

| Check | Result | File |
|---|---|---|
| Inference scaled to 0 (T8) | Gateway answers `503 UPSTREAM_UNAVAILABLE` in 2.05 s instead of hanging; 200 again after scaling back | [`04-scale-to-zero.txt`](docs/evidence/m2/minikube/04-scale-to-zero.txt) |
| Load balancing, 30 uploads 10 at a time (T10, T13) | All 200; served 7 / 14 / 9 by the three replicas; each sidecar's `/metrics` agrees (p50 ≈ 10--15 ms) | [`05-load-balancing.txt`](docs/evidence/m2/minikube/05-load-balancing.txt) |
| `kubectl delete -f` + `kubectl apply -f` (T12) | Stack back with no manual steps; smoke test 17/17 | [`06-rebuild.txt`](docs/evidence/m2/minikube/06-rebuild.txt) |

## Sidecar rationale

Each inference pod runs a **metrics-exporter** sidecar next to the model server. The model server
appends one JSON line per request to a file on an `emptyDir` volume the two containers share, and
the sidecar turns it into Prometheus metrics (request count, errors, p50/p95 latency) on port 9100.
It has to live in the same pod because a shared `emptyDir` only exists within one pod, and because
metrics must describe *this* replica: comparing the three replicas' counts is what shows the
Service is spreading load, while the model server itself stays free of metrics code.

## Tests

- **Unit tests** (55, pytest): `docker run --rm -v "$PWD/services-src:/src" -w /src python:3.11-slim sh -c "pip install -q -r requirements-dev.txt && pytest -q"`
- **API smoke test** (17 checks: happy path, retrieval, 413/415/400/404 cases, UI): `scripts/smoke.sh`
- **Operational evidence** (scaling, self-healing, scale-to-zero, load balancing, rebuild): `scripts/evidence.sh`

Uploads made by the scripts carry `source=test`, so the web UI lists only real uploads.

## Deviations from the Milestone 1 design

| M1 design | M2 implementation | Why |
|---|---|---|
| Single-node Minikube | 3-node k3s on FABRIC (Minikube kept for development) | The course deploys on FABRIC; more than one node also makes replica spreading and self-healing visible |
| Images loaded with `minikube image load` | Images on GHCR (`ghcr.io/angeudybp/kubebalancer-*:0.2.0`); `fabric/load-images.sh` as fallback | FABRIC nodes need a registry |
| Mock inference in M2, real model in M3 | Real MobileNetV2 (`mobilenetv2-12`, ONNX Model Zoo) already in M2; `MOCK_MODE=1` kept for unit tests | Ahead of schedule: real labels make the demo meaningful |
| No UI | React web UI served by the gateway at `/` | Easier demonstration; still one external Service |
| Storage on a PVC | `emptyDir`; data is lost when the storage pod is replaced | Persistence is M3 scope; only the volume definition changes |
| Resource limits (§3.7) | Not set yet | Planned for M3 |
| Gateway → inference timeout 15 s | Plus a 2 s connect timeout | A Service with no endpoints dropped connections, so a scaled-to-zero tier took 15 s to fail; it now fails in about 2 s |
| (not specified) | Gateway opens a new connection per downstream call | kube-proxy balances per connection; a reused connection sent every request to one replica |
