"""inference: return the top labels for a 224x224 image.

Milestone 2 runs in mock mode only (MOCK_MODE=1): the "prediction" is derived
from a hash of the image bytes, so it is repeatable and needs no model. Every
response carries "mock": true so fake results are never mistaken for real ones.
The real MobileNetV2 ONNX model arrives in Milestone 3.

Each request appends one JSON line to REQUEST_LOG; the metrics-exporter
sidecar in the same pod tails that file (M1 report §3.2).
"""
import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import random
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Request
from pydantic import BaseModel, Field

from kb_common import ApiError, create_app, request_id

MOCK_MODE = os.getenv("MOCK_MODE", "1") == "1"
MODEL_VERSION = "mock-0.2.0"
REQUEST_LOG = Path(os.getenv("REQUEST_LOG", "/var/log/app/requests.jsonl"))
# Simulated model-load time, to show that readiness holds traffic back (test T14).
STARTUP_DELAY_SECONDS = float(os.getenv("STARTUP_DELAY_SECONDS", "0"))
POD_NAME = os.getenv("POD_NAME", socket.gethostname())
NODE_NAME = os.getenv("NODE_NAME", "unknown")

# A handful of real ImageNet class names, so mock output looks like the real thing.
LABELS = [
    "golden retriever", "Labrador retriever", "tabby cat", "Egyptian cat", "red fox",
    "goldfish", "macaw", "monarch butterfly", "sports car", "school bus",
    "mountain bike", "espresso", "pizza", "banana", "volcano", "lakeside",
]

log = logging.getLogger("inference")


def mock_predict(image: bytes, top_k: int) -> list[dict]:
    """Deterministic fake scores: the same image always gets the same labels."""
    rng = random.Random(hashlib.sha256(image).digest())
    raw = [rng.random() ** 4 for _ in LABELS]  # The power sharpens the distribution.
    total = sum(raw)
    ranked = sorted(zip(LABELS, raw), key=lambda pair: pair[1], reverse=True)
    return [{"label": label, "score": round(score / total, 4)} for label, score in ranked[:top_k]]


def write_request_log(entry: dict) -> None:
    try:
        REQUEST_LOG.parent.mkdir(parents=True, exist_ok=True)
        with REQUEST_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        # Metrics are best-effort; a full or missing log volume must not fail predictions.
        log.warning("could not write request log %s", REQUEST_LOG, exc_info=True)


@asynccontextmanager
async def lifespan(app):
    if not MOCK_MODE:
        log.error("MOCK_MODE=0 but no model is bundled until Milestone 3; staying not-ready")
    else:
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        app.state.ready = True
        log.info("ready (mock mode, model %s, pod %s on %s)", MODEL_VERSION, POD_NAME, NODE_NAME)
    yield


app = create_app("inference", lifespan=lifespan, ready=False)


class PredictRequest(BaseModel):
    data: str = Field(description="Base64-encoded 224x224 JPEG")
    topK: int = Field(default=3, ge=1, le=10)


@app.post("/predict")
async def predict(body: PredictRequest, request: Request):
    start = time.perf_counter()
    outcome, top = "error", []
    try:
        try:
            image = base64.b64decode(body.data, validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(400, "BAD_REQUEST", "data is not valid base64")
        if not image:
            raise ApiError(400, "BAD_REQUEST", "data is empty")
        top = mock_predict(image, body.topK)
        outcome = "ok"
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        write_request_log({
            "ts": time.time(),
            "requestId": request_id(request),
            "pod": POD_NAME,
            "latencyMs": round(latency_ms, 3),
            "outcome": outcome,
            "label": top[0]["label"] if top else None,
        })

    return {
        "label": top[0]["label"],
        "confidence": top[0]["score"],
        "topK": top,
        "modelVersion": MODEL_VERSION,
        "mock": True,
        "podName": POD_NAME,
        "nodeName": NODE_NAME,
    }
