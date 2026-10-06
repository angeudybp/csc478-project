# KubeClassify --- Image Classification Pipeline on Kubernetes

CSC 478 course project. A four-service image classification pipeline deployed on a single-node
Minikube cluster: upload an image to one public endpoint, get back a predicted label, and retrieve
the original image, the processed image, and the prediction afterwards by identifier.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M1 --- Architecture** | Design only: components, Services, API contracts, persistence plan, risk and test plan | **Complete** --- see [`docs/report/Milestone1-Report.pdf`](docs/report/Milestone1-Report.pdf) |
| M2 --- Core implementation | Deployments, Services, sidecar, scaling and self-healing. No persistence | Not started |
| M3 --- Persistence and demo | PV/PVC, probes, resource limits, demo video, final report | Not started |

## Architecture at a glance

Four Deployments in the `imgpipe` namespace. `gateway` is the single external entrypoint
(NodePort 30080) and orchestrates the pipeline; `preprocess` normalizes images to 224x224;
`inference` runs MobileNetV2 via ONNX Runtime and is the scaling target at 3 replicas, carrying a
metrics-exporter sidecar in the same pod; `storage` owns the only PersistentVolumeClaim.

Full design, diagrams, and API contracts: `docs/report/Milestone1-Report.pdf`.

## Building the report

```bash
make report      # renders diagrams, then the PDF -> docs/report/Milestone1-Report.pdf
make diagrams    # diagrams only
make check       # verify page count and fonts
make clean       # remove generated PDFs
```

Requirements: `pandoc`, `xelatex` (TeX Live), and `npx` (mermaid-cli is fetched on demand).
If `pandoc` is not on `PATH`, the Makefile falls back to `~/.local/bin/pandoc`.

## Layout

```
docs/milestone1/   report sections, numbered -- pandoc concatenates them in filename order
docs/diagrams/     Mermaid sources (.mmd) and rendered PDFs in out/
docs/report/       pandoc metadata (margins, font size) and the built PDF
```

`deployments/`, `services/`, `storage/`, and `services-src/` arrive in Milestone 2; their intended
layout is specified in the Milestone 1 report.
