# Use Cases and Workflow

Three user stories define the scope of the system. US-1 and US-2 are end-user facing and together
describe the full data path; US-3 is operator-facing and is what makes the system a Kubernetes
project rather than a web application. Each story carries acceptance criteria that map directly
onto rows of the test matrix in §6.3.

## US-1 — Classify an uploaded image

> **As a** user, **I want to** upload an image to a single public endpoint and receive a predicted
> label with a confidence score, **so that** I can classify images without installing anything.

**Acceptance criteria**

- `POST /api/v1/images` with a JPEG or PNG under 8 MB returns HTTP 200 with a JSON body containing
  `imageId`, `label`, `confidence`, and a `topK` list of the three highest-scoring classes.
- The response includes per-stage timings, so the cost of each hop is visible to the caller.
- An upload over the size limit is rejected with HTTP 413 and a structured error body; an upload
  that is not a decodable image is rejected with HTTP 415. Neither causes a pod restart.
- *Verified by:* T1, T2, T3, T4, T5, T6.

## US-2 — Retrieve a past classification

> **As a** user, **I want to** retrieve a previous prediction and both image variants by their
> identifier, **so that** results are durable and auditable after the fact.

**Acceptance criteria**

- `GET /api/v1/results/{imageId}` returns the stored prediction JSON for any previously accepted
  upload, and HTTP 404 for an unknown identifier.
- `GET /api/v1/images/{imageId}?variant=original` and `?variant=processed` each return the
  corresponding image bytes with the correct content type.
- Results survive the destruction and recreation of the storage pod: the same identifiers remain
  retrievable, byte-for-byte, after the pod is deleted and rescheduled.
- *Verified by:* T7, T11.

## US-3 — Scale and survive failure

> **As the** operator, **I want to** scale the inference tier and lose individual pods without
> dropping user traffic, **so that** the service stays available under load and during failures.

**Acceptance criteria**

- The inference Deployment scales from 1 to 3 replicas with all replicas reaching `Ready`, and
  requests are observably distributed across them via the per-pod metrics sidecar.
- Manually deleting an inference pod results in automatic recreation by the Deployment
  controller, with no failed user requests while the remaining replicas serve traffic.
- With the inference tier scaled to zero, the gateway returns a well-formed HTTP 503 rather than
  hanging or crashing, and recovers automatically when replicas return.
- A full teardown and reprovision (`kubectl delete -f . && kubectl apply -f .`) brings the whole
  stack back to `Ready` without manual intervention.
- *Verified by:* T8, T9, T10, T12, T13.

## Data flow

Figure 1 shows the request path for both stories. The write path (US-1) is a single synchronous
request that fans through three internal services before responding. The read path (US-2) touches
only the gateway and the storage service. The storage service is the sole holder of persistent
state, and the sole component that is never exposed outside the cluster.

![**KubeBalancer data flow.** The write path (solid, numbered) runs upload → preprocess → inference → persist → response. The read path (dashed) serves retrieval from the persistent volume. Only the gateway is reachable from outside the cluster.](docs/diagrams/out/dataflow.pdf){width=100%}
