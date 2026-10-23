"""storage: the only service that keeps state.

Saves the original upload, the 224x224 model input, and the prediction record
under DATA_DIR, using the layout from the M1 report §5:

    originals/<yyyy>/<mm>/<dd>/<imageId>.<ext>
    processed/<yyyy>/<mm>/<dd>/<imageId>.jpg
    results/<imageId>.json
    index/manifest.jsonl          one line per new result, append-only

In Milestone 2 DATA_DIR is an emptyDir, so data is lost when the pod goes away.
Milestone 3 mounts a PersistentVolumeClaim at the same path; nothing here changes.
Storage runs as a single replica, so this process is the only writer.
"""
import json
import os
import re
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from kv_common import ApiError, create_app

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
MAX_OBJECT_BYTES = 9 * 1024 * 1024  # Uploads are capped at 8 MB by the gateway; leave headroom.

IMAGE_ID = re.compile(r"^img_[A-Za-z0-9]{1,40}$")  # Also prevents path traversal via the ID.
VARIANTS = {"original": "originals", "processed": "processed"}
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png"}
CONTENT_TYPES = {f".{ext}": ctype for ctype, ext in EXTENSIONS.items()}

_index_lock = threading.Lock()
_object_paths: dict[tuple[str, str], Path] = {}


def _check_id(image_id: str) -> None:
    if not IMAGE_ID.match(image_id):
        raise ApiError(400, "BAD_REQUEST", "Invalid imageId")


def _variant_dir(variant: str) -> str:
    if variant not in VARIANTS:
        raise ApiError(400, "BAD_REQUEST", "variant must be 'original' or 'processed'")
    return VARIANTS[variant]


def _atomic_write(path: Path, data: bytes) -> None:
    """Write via a temp file and rename, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _find_object(image_id: str, variant: str) -> Path | None:
    cached = _object_paths.get((image_id, variant))
    if cached and cached.exists():
        return cached
    # Not written by this process (e.g. after a restart with a persistent volume): search for it.
    for path in (DATA_DIR / _variant_dir(variant)).glob(f"*/*/*/{image_id}.*"):
        if not path.name.endswith(".tmp"):
            _object_paths[(image_id, variant)] = path
            return path
    return None


def save_object(image_id: str, variant: str, data: bytes, content_type: str) -> Path:
    ext = EXTENSIONS.get(content_type)
    if ext is None:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Objects must be image/jpeg or image/png")
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    existing = _find_object(image_id, variant)
    path = existing if existing and existing.suffix == f".{ext}" else \
        DATA_DIR / _variant_dir(variant) / day / f"{image_id}.{ext}"
    _atomic_write(path, data)
    _object_paths[(image_id, variant)] = path
    return path


def save_result(image_id: str, record: dict) -> bool:
    """Save a prediction record; returns True if it is new. Saving an ID again overwrites it."""
    path = DATA_DIR / "results" / f"{image_id}.json"
    is_new = not path.exists()
    _atomic_write(path, json.dumps(record).encode())
    if is_new:
        with _index_lock:
            index = DATA_DIR / "index" / "manifest.jsonl"
            index.parent.mkdir(parents=True, exist_ok=True)
            with index.open("a") as f:
                f.write(json.dumps({"imageId": image_id, "savedAt": record.get("createdAt")}) + "\n")
    return is_new


def load_result(image_id: str) -> dict | None:
    path = DATA_DIR / "results" / f"{image_id}.json"
    try:
        return json.loads(path.read_bytes())
    except FileNotFoundError:
        return None


def list_results(limit: int) -> list[dict]:
    index = DATA_DIR / "index" / "manifest.jsonl"
    if not index.exists():
        return []
    with index.open() as f:
        recent = deque(f, maxlen=limit)
    results = []
    for line in reversed(recent):
        try:
            record = load_result(json.loads(line)["imageId"])
        except (ValueError, KeyError):
            continue
        if record is not None:
            results.append(record)
    return results


@asynccontextmanager
async def lifespan(app):
    for sub in ("originals", "processed", "results", "index"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    app.state.ready = True
    yield


app = create_app("storage", lifespan=lifespan, ready=False)


@app.put("/objects/{image_id}/{variant}", status_code=201)
async def put_object(image_id: str, variant: str, request: Request):
    _check_id(image_id)
    _variant_dir(variant)
    data = await request.body()
    if not data:
        raise ApiError(400, "EMPTY_UPLOAD", "Object body is empty")
    if len(data) > MAX_OBJECT_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Object is too large")
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    path = await run_in_threadpool(save_object, image_id, variant, data, content_type)
    return {"imageId": image_id, "variant": variant, "bytes": len(data),
            "path": str(path.relative_to(DATA_DIR))}


@app.get("/objects/{image_id}/{variant}")
async def get_object(image_id: str, variant: str):
    _check_id(image_id)
    _variant_dir(variant)
    path = await run_in_threadpool(_find_object, image_id, variant)
    if path is None:
        raise ApiError(404, "NOT_FOUND", f"No {variant} image for {image_id}")
    data = await run_in_threadpool(path.read_bytes)
    return Response(content=data, media_type=CONTENT_TYPES.get(path.suffix, "application/octet-stream"))


@app.put("/results/{image_id}")
async def put_result(image_id: str, request: Request):
    _check_id(image_id)
    try:
        record = await request.json()
    except ValueError:
        raise ApiError(400, "BAD_REQUEST", "Body must be JSON")
    if not isinstance(record, dict):
        raise ApiError(400, "BAD_REQUEST", "Body must be a JSON object")
    record["imageId"] = image_id
    created = await run_in_threadpool(save_result, image_id, record)
    return Response(status_code=201 if created else 200, content=json.dumps(record),
                    media_type="application/json")


@app.get("/results/{image_id}")
async def get_result(image_id: str):
    _check_id(image_id)
    record = await run_in_threadpool(load_result, image_id)
    if record is None:
        raise ApiError(404, "NOT_FOUND", f"No result for {image_id}")
    return record


@app.get("/results")
async def get_results(limit: int = Query(default=20, ge=1, le=100)):
    return {"results": await run_in_threadpool(list_results, limit)}
