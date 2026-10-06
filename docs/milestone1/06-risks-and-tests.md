# Risk and Test Plan

## Risk register

Eight risks are tracked. Each has a mitigation that is already reflected in the architecture rather
than deferred, and each maps to the test that would detect it if the mitigation failed.

| # | Risk | L | I | Mitigation (already in the design) | Detected by |
|:--:|:------------------------|:--:|:--:|:---------------------------------|:-----:|
| R1 | **Model size and cold start.** A large runtime image slows scheduling and risks `ImagePullBackOff` or `ErrImageNeverPull` on a local cluster. | M | M | ONNX Runtime with MobileNetV2 (~14 MB weights) on `python:3.11-slim`; weights baked into the image, not downloaded at startup; `minikube image load` with `imagePullPolicy: IfNotPresent`. | T12 |
| R2 | **Timeout cascade.** Three chained hops let one slow dependency hang the client connection. | M | H | Per-hop budgets summing to less than the client budget (Table 3); retry on connection errors only, never on 5xx. | T8 |
| R3 | **OOMKilled under replication.** Three inference replicas on one node, each sizing an ONNX thread pool to the host core count, exhaust node memory or thrash the CPU. | M | H | Explicit requests and limits (256 Mi/250 m → 768 Mi/1000 m) plus `OMP_NUM_THREADS=1` per replica. | T10, T13 |
| R4 | **ReadWriteOnce volume versus scaling.** Any attempt to run two storage pods deadlocks on multi-attach. | L | H | Storage pinned to one replica with `strategy: Recreate`; constraint documented in §5.3 as a design cost. | T11 |
| R5 | **Traffic before the model is loaded.** A pod that is `Running` but not yet able to infer receives requests and returns 503s on every scale-up. | H | M | Separate `/healthz` and `/readyz`; readiness gated on completed model load. | T9, T10 |
| R6 | **Decompression bombs and oversized uploads.** A small file can decode to gigabytes of pixels and exhaust the preprocessor. | M | H | 8 MB limit enforced at the gateway *before* the body is buffered; MIME allowlist; `Pillow.MAX_IMAGE_PIXELS` guard in the preprocessor. | T2, T4, T5 |
| R7 | **Grading reproducibility.** The brief requires `kubectl delete -f . && kubectl apply -f .` to cleanly reprovision; dependency ordering or a stale NodePort binding can break it. | M | H | Numerically prefixed manifests applied in dependency order; dedicated `imgpipe` namespace; fixed NodePort 30080 checked for conflicts. | T12 |
| R8 | **Solo schedule risk.** A single developer blocked on the ML path stops all progress on orchestration, which is what the project is actually graded on. | M | M | `MOCK_MODE` deterministic classifier means the full pipeline can be built, deployed, and tested with no model present. | T1 |

: **Risk register.** L = likelihood, I = impact, on a Low/Medium/High scale.

The two risks taken most seriously are R2 and R5, because both produce *intermittent* failures that
are easy to misread as flakiness. R5 in particular is the failure most likely to appear during the
Milestone 3 demonstration, when pods are being deliberately deleted on camera.

## Test approach

Testing is layered, and the layers are kept separate so a failure localizes immediately:

- **Unit** — pure transform logic per service: resize correctness, EXIF stripping, label decoding,
  path construction. Runs with `pytest`, no network, no cluster.
- **Contract** — each service started alone in a container and exercised with `curl` against the
  contracts in §4. This is where a mismatch between two services is caught, before they are wired
  together.
- **Integration** — the full pipeline on the cluster through the NodePort endpoint, driven by a
  shell script committed to the repository so it is reproducible by a grader rather than described.
- **Operational** — scaling, pod deletion, and persistence survival, verified with `kubectl` and
  captured as command output.

Throughout Milestone 2 the inference service runs with `MOCK_MODE=1` so that orchestration
failures are never confused with model failures. The real MobileNetV2 graph is enabled and the
suite re-run before the Milestone 3 demonstration.

## Test matrix

| ID | Case | Input / action | Expected result | When |
|:---:|:-------------------|:----------------------|:------------------------------|:--:|
| T1 | Happy path | 500 KB JPEG of a dog | 200; plausible label with confidence; three artifacts written | M2 |
| T2 | Oversized upload | 12 MB JPEG | 413 `PAYLOAD_TOO_LARGE`; no pod restart; memory flat | M2 |
| T3 | At-limit upload | 7.5 MB JPEG | 200 within the 30 s client budget | M2 |
| T4 | Invalid image | `.txt` file renamed `.jpg` | 415 `UNSUPPORTED_MEDIA_TYPE`; structured error; no crash | M2 |
| T5 | Unsupported format | GIF, then SVG | 415 for both; allowlist holds | M2 |
| T6 | Empty upload | Zero-byte file | 400 `EMPTY_UPLOAD` | M2 |
| T7 | Unknown identifier | `GET /results/img_doesnotexist` | 404 `NOT_FOUND` | M2 |
| T8 | Dependency unavailable | `kubectl scale --replicas=0 deploy/inference` | 503 `UPSTREAM_UNAVAILABLE` promptly, not a hang; full recovery when scaled back | M2 |
| T9 | Self-healing | `kubectl delete pod <one inference pod>` | Deployment recreates it; concurrent requests keep succeeding on the surviving replicas | M2 |
| T10 | Scaling | `kubectl scale --replicas=3 deploy/inference` | All three `Ready`; all three sidecar `:9100` endpoints report non-zero, roughly balanced counts | M2 |
| T11 | Persistence survival | Upload 3, delete storage pod, re-request | Identical bytes and JSON after recreation (§5.4) | M3 |
| T12 | Clean reprovision | `kubectl delete -f . && kubectl apply -f .` | Every pod `Ready`, endpoint serving, no manual steps | M2 |
| T13 | Concurrency | 10 parallel uploads | All return 200; p95 recorded as the first *measured* latency figure in the project | M2 |
| T14 | Probe correctness | Restart inference, poll `/readyz` during startup | `/readyz` returns non-200 until the model is loaded; no request is routed to a not-ready pod | M2 |

: **Test matrix.** M2 tests run at Milestone 2; M3 tests require the persistent volume.

T13 deserves a note: it is the first point at which this project produces a measured performance
number. Until it runs, every latency figure in this report is a budget (Table 3), and the Milestone
3 report will present measured values beside those budgets so the gap is visible either way.
