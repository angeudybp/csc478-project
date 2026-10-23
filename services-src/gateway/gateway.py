"""gateway: the only public entrypoint. Validates uploads and runs the pipeline.

POST /api/v1/images  ->  preprocess -> inference -> storage  ->  prediction
Downstream services are reached by Service DNS name, with the per-hop
timeouts and retry rules from the M1 report, Table 3.
"""
import base64
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import File, Query, Request, UploadFile
from fastapi.responses import Response

from kb_common import REQUEST_ID_HEADER, ApiError, create_app, request_id

PREPROCESS_URL = os.getenv("PREPROCESS_URL", "http://preprocess-svc:8081")
INFERENCE_URL = os.getenv("INFERENCE_URL", "http://inference-svc:8082")
STORAGE_URL = os.getenv("STORAGE_URL", "http://storage-svc:8083")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MULTIPART_OVERHEAD = 64 * 1024
TOP_K = 3

# httpx logs every outbound request at INFO; the request-ID middleware already logs each hop.
logging.getLogger("httpx").setLevel(logging.WARNING)

# (timeout seconds, retry once on a failed connection?) -- M1 report Table 3.
PREPROCESS_HOP = (5.0, True)
INFERENCE_HOP = (15.0, False)  # Never retry: re-sending to a slow tier makes it slower.
STORAGE_HOP = (5.0, True)

MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


def sniff_content_type(data: bytes) -> str | None:
    """Trust the file's first bytes, not its name or the client's Content-Type."""
    for magic, ctype in MAGIC.items():
        if data.startswith(magic):
            return ctype
    return None


def new_image_id() -> str:
    """Time-ordered ID: 12 hex digits of epoch milliseconds plus 8 random hex digits."""
    return f"img_{int(time.time() * 1000):012X}{secrets.token_hex(4).upper()}"


@asynccontextmanager
async def lifespan(app):
    app.state.client = httpx.AsyncClient()
    yield
    await app.state.client.aclose()


# Obviously oversized uploads are refused from Content-Length alone, before the body is read.
app = create_app("gateway", lifespan=lifespan,
                 body_limits={"/api/v1/images": MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD})


async def call(request: Request, service: str, hop: tuple[float, bool], method: str, url: str,
               **kwargs) -> httpx.Response:
    """Call a downstream service, mapping network failures to 503/504 and errors to 502."""
    timeout, retry = hop
    headers = {REQUEST_ID_HEADER: request_id(request), **kwargs.pop("headers", {})}
    client: httpx.AsyncClient = request.app.state.client
    for attempt in (1, 2):
        try:
            response = await client.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # No ready endpoints behind the Service (e.g. scaled to 0) or pod just went away.
            if retry and attempt == 1:
                continue
            raise ApiError(503, "UPSTREAM_UNAVAILABLE", f"{service} is unavailable")
        except httpx.TimeoutException:
            raise ApiError(504, "UPSTREAM_TIMEOUT", f"{service} did not respond within {timeout:g} s")
        except httpx.HTTPError:
            raise ApiError(502, "UPSTREAM_FAILED", f"{service} connection failed")
        if response.status_code == 503:
            raise ApiError(503, "UPSTREAM_UNAVAILABLE", f"{service} is unavailable")
        return response
    raise AssertionError("unreachable")


def upstream_failed(service: str, response: httpx.Response) -> ApiError:
    return ApiError(502, "UPSTREAM_FAILED", f"{service} returned {response.status_code}")


@app.post("/api/v1/images")
async def upload_image(request: Request, file: UploadFile | None = File(default=None)):
    started = time.perf_counter()

    # 1. Validate.
    if file is None:
        raise ApiError(400, "EMPTY_UPLOAD", "Missing multipart field 'file'")
    original = await file.read(MAX_UPLOAD_BYTES + 1)
    if not original:
        raise ApiError(400, "EMPTY_UPLOAD", "Uploaded file is empty")
    if len(original) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Upload exceeds 8 MB")
    content_type = sniff_content_type(original)
    if content_type is None:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Only JPEG and PNG images are accepted")

    timings = {}

    # 2. Preprocess.
    t = time.perf_counter()
    r = await call(request, "preprocess", PREPROCESS_HOP, "POST", f"{PREPROCESS_URL}/preprocess",
                   content=original, headers={"Content-Type": content_type})
    if r.status_code == 415:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Not a valid JPEG or PNG image")
    if r.status_code != 200:
        raise upstream_failed("preprocess", r)
    processed = r.json()
    timings["preprocessMs"] = round((time.perf_counter() - t) * 1000)

    # 3. Infer.
    t = time.perf_counter()
    r = await call(request, "inference", INFERENCE_HOP, "POST", f"{INFERENCE_URL}/predict",
                   json={"data": processed["data"], "topK": TOP_K})
    if r.status_code != 200:
        raise upstream_failed("inference", r)
    prediction = r.json()
    timings["inferenceMs"] = round((time.perf_counter() - t) * 1000)

    # 4. Store the original, the processed image, and the prediction record.
    image_id = new_image_id()
    t = time.perf_counter()
    for variant, body, ctype in (
        ("original", original, content_type),
        ("processed", base64.b64decode(processed["data"]), "image/jpeg"),
    ):
        r = await call(request, "storage", STORAGE_HOP, "PUT",
                       f"{STORAGE_URL}/objects/{image_id}/{variant}",
                       content=body, headers={"Content-Type": ctype})
        if r.status_code not in (200, 201):
            raise upstream_failed("storage", r)

    timings["storageMs"] = round((time.perf_counter() - t) * 1000)
    timings["totalMs"] = round((time.perf_counter() - started) * 1000)
    record = {
        "imageId": image_id,
        "label": prediction["label"],
        "confidence": prediction["confidence"],
        "topK": prediction["topK"],
        "modelVersion": prediction["modelVersion"],
        "mock": prediction["mock"],
        "filename": file.filename,
        "originalSize": {"width": processed["originalWidth"], "height": processed["originalHeight"]},
        "servedBy": {"inferencePod": prediction.get("podName"),
                     "inferenceNode": prediction.get("nodeName")},
        "timings": timings,
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "requestId": request_id(request),
    }
    r = await call(request, "storage", STORAGE_HOP, "PUT", f"{STORAGE_URL}/results/{image_id}",
                   json=record)
    if r.status_code not in (200, 201):
        raise upstream_failed("storage", r)
    return record


async def _from_storage(request: Request, path: str) -> httpx.Response:
    r = await call(request, "storage", STORAGE_HOP, "GET", f"{STORAGE_URL}{path}")
    if r.status_code in (400, 404):
        body = r.json().get("error", {})
        raise ApiError(r.status_code, body.get("code", "NOT_FOUND"), body.get("message", "Not found"))
    if r.status_code != 200:
        raise upstream_failed("storage", r)
    return r


@app.get("/api/v1/results/{image_id}")
async def get_result(image_id: str, request: Request):
    return (await _from_storage(request, f"/results/{image_id}")).json()


@app.get("/api/v1/results")
async def list_results(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    return (await _from_storage(request, f"/results?limit={limit}")).json()


@app.get("/api/v1/images/{image_id}")
async def get_image(image_id: str, request: Request,
                    variant: str = Query(default="original", pattern="^(original|processed)$")):
    r = await _from_storage(request, f"/objects/{image_id}/{variant}")
    return Response(content=r.content, media_type=r.headers.get("content-type"))
