# API Contracts

All four services speak JSON over HTTP and are implemented with FastAPI on Python 3.11, so each
publishes a machine-readable OpenAPI document at `/openapi.json` and interactive documentation at
`/docs`. The contracts below are the authoritative definitions for Milestone 2.

Two conventions apply to every endpoint on every service:

- **Request correlation.** The gateway generates an `X-Request-Id` for each inbound request (or
  honours a client-supplied one) and forwards it on every internal call. All four services include
  it in their log lines and in error responses.
- **Uniform error envelope.** Every non-2xx response has the same shape, so the gateway can
  translate a downstream failure without inventing a format:

  ```json
  { "error": { "code": "PAYLOAD_TOO_LARGE",
               "message": "Upload exceeds the 8388608 byte limit" },
    "requestId": "7f3c1e9a" }
  ```

> **Note on the figures below.** Latency values in these examples are *illustrative placeholders*
> showing the response shape. No latency in this document has been measured; see Table 3.

## Gateway (external — the only public API)

### `POST /api/v1/images` — classify an image

Accepts `multipart/form-data` with a single file field. Maximum 8 MB; `image/jpeg` and `image/png`
only.

```bash
curl -s -X POST "http://$(minikube ip):30080/api/v1/images" \
     -F "file=@samples/retriever.jpg;type=image/jpeg"
```

```json
{ "imageId": "img_01JAR7K2M9QX4T8B",
  "label": "golden retriever",
  "confidence": 0.8734,
  "topK": [ { "label": "golden retriever",   "score": 0.8734 },
            { "label": "Labrador retriever", "score": 0.0612 },
            { "label": "kuvasz",             "score": 0.0188 } ],
  "modelVersion": "mobilenetv2-1.0-onnx",
  "mock": false,
  "timings": { "preprocessMs": 38, "inferenceMs": 121,
               "storageMs": 44, "totalMs": 207 },
  "requestId": "7f3c1e9a" }
```

### `GET /api/v1/results/{imageId}` — retrieve a stored prediction

Returns the persisted prediction record, which is the response body above plus a `storedAt`
timestamp and the storage paths of both image variants. Returns 404 for an unknown identifier.

### `GET /api/v1/images/{imageId}?variant=original|processed` — retrieve image bytes

Returns the raw image with the appropriate `Content-Type`. `variant` defaults to `original`.
Returns 404 if the identifier or the requested variant does not exist.

### `GET /api/v1/results?limit=20` — list recent classifications

Returns `{ "items": [ ... ], "count": 20 }`, newest first, backed by the append-only index
described in §5.2. Supports `limit` between 1 and 100, defaulting to 20.

### Gateway status codes

| Code | `error.code` | Condition |
|:----:|:--------------------------|:--------------------------------------------|
| 200 | — | Classification or retrieval succeeded. |
| 400 | `EMPTY_UPLOAD` | Zero-byte file, or the `file` field is absent. |
| 404 | `NOT_FOUND` | Unknown `imageId`, or variant not stored. |
| 413 | `PAYLOAD_TOO_LARGE` | Upload exceeds 8 MB. Rejected before the body is buffered. |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Content type not in the allowlist, or bytes are not a decodable image. |
| 502 | `UPSTREAM_FAILED` | A downstream service returned 5xx. Not retried (§3.5). |
| 503 | `UPSTREAM_UNAVAILABLE` | No healthy replica of a required service. |
| 504 | `UPSTREAM_TIMEOUT` | A downstream hop exceeded its budget from Table 3. |

: **Gateway response codes.**

## Preprocess (internal)

### `POST /preprocess`

Takes raw image bytes — not multipart — with the content type in the header. Decodes, strips EXIF
metadata, converts to RGB, resizes to 224×224, and re-encodes as JPEG at quality 90.

```http
POST /preprocess HTTP/1.1
Content-Type: image/jpeg
X-Request-Id: 7f3c1e9a

<raw image bytes>
```

```json
{ "width": 224, "height": 224, "format": "jpeg", "colorspace": "RGB",
  "bytes": 18442, "sourceWidth": 1600, "sourceHeight": 1200,
  "data": "/9j/4AAQSkZJRgABAQEAYABgAAD...<base64, truncated>" }
```

Returns 415 with `UNSUPPORTED_MEDIA_TYPE` if the bytes do not decode as an image, and 413 if the
decoded pixel count exceeds the decompression-bomb guard (§6.1, R6).

## Inference (internal)

### `POST /predict`

```json
{ "data": "/9j/4AAQSkZJRgABAQEAYABgAAD...<base64 224x224 JPEG>", "topK": 3 }
```

```json
{ "predictions": [ { "label": "golden retriever",   "score": 0.8734 },
                   { "label": "Labrador retriever", "score": 0.0612 },
                   { "label": "kuvasz",             "score": 0.0188 } ],
  "modelVersion": "mobilenetv2-1.0-onnx",
  "mock": false,
  "latencyMs": 121 }
```

`topK` defaults to 3 and is capped at 10. The `mock` field reports whether the response came from
the real MobileNetV2 graph or from the deterministic mock classifier — when `MOCK_MODE=1`, the
service derives a stable label from a hash of the input bytes, so tests are repeatable and need no
model loaded. The field is part of the contract rather than hidden configuration, so no result can
be mistaken for a real prediction.

### `GET /metrics` — served by the sidecar on port 9100

Prometheus text format, per replica:

```
kubebalancer_inference_requests_total 143
kubebalancer_inference_errors_total 2
kubebalancer_inference_latency_ms{quantile="0.5"} 118
kubebalancer_inference_latency_ms{quantile="0.95"} 186
```

## Storage (internal)

| Method and path | Request body | Success | Purpose |
|:-------------------------------|:-----------|:----:|:-------------------------|
| `PUT /objects/{imageId}/{variant}` | raw bytes | 201 | Store an image variant. Returns its path and byte count. |
| `GET /objects/{imageId}/{variant}` | — | 200 | Retrieve image bytes. |
| `PUT /results/{imageId}` | JSON record | 201 | Store the prediction record and append to the index. |
| `GET /results/{imageId}` | — | 200 | Retrieve one prediction record. |
| `GET /results?limit=n` | — | 200 | List recent records, newest first. |

: **Storage service endpoints.** `{variant}` is `original` or `processed`.

Writes are idempotent on `imageId`: re-`PUT`ting the same identifier overwrites in place and does
not duplicate the index entry.

## Health and readiness (all services)

| Endpoint | Probe | Returns 200 when |
|:-----------|:-----------|:------------------------------------------------|
| `GET /healthz` | liveness | The process is running and the event loop is responsive. Never checks dependencies — a liveness probe that fails on a dependency outage causes a restart storm. |
| `GET /readyz` | readiness | The service can serve traffic. On `inference`, only after the ONNX model is loaded; on `storage`, only after `/data` is mounted and writable. |

: **Probe endpoints.**
