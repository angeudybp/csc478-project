# KubeBalancer --- Image Classification Pipeline on Kubernetes

CSC 478 (Cloud Engineering) course project. A four-service image classification pipeline deployed
on a single-node Minikube cluster: upload an image to one public endpoint, get back a predicted
label, and retrieve the original image, the processed image, and the prediction afterwards by ID.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M1 --- Architecture** | Design only: components, Services, API contracts, persistence plan, risk and test plan | **Complete** --- see [`docs/report/Milestone1-Report.pdf`](docs/report/Milestone1-Report.pdf) |
| M2 --- Core implementation | Deployments, Services, sidecar, scaling and self-healing. No persistence | Not started |
| M3 --- Persistence and demo | PV/PVC, probes, resource limits, demo video, final report | Not started |

## Architecture at a glance

Four Deployments in the `imgpipe` namespace. `gateway` is the single external entrypoint
(NodePort 30080) and calls the other services in order; `preprocess` resizes images to 224x224;
`inference` runs MobileNetV2 with ONNX Runtime and is scaled to 3 replicas, each with a
metrics-exporter sidecar; `storage` owns the only PersistentVolumeClaim.

## Repository layout

```
docs/report/       Milestone 1 report: Word source (.docx) and submitted PDF
docs/diagrams/     Mermaid diagram sources (.mmd) and rendered diagrams in out/
```

The Word document is the editable source of the report; the PDF is exported from it.

`deployments/`, `services/`, `storage/`, and `services-src/` arrive in Milestone 2; their intended
layout is described in the Milestone 1 report (section 3.8).
