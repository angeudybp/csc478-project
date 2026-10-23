"""inference: return the top labels for a 224x224 image.

By default this runs MobileNetV2 (ImageNet-1k, 1000 classes) with ONNX Runtime on
CPU. The model file is built into the image, so pods never download it. The pod
reports ready only after the model has loaded (M1 report §3.7, test T14).

MOCK_MODE=1 skips the model and derives repeatable fake labels from a hash of the
image bytes; every response carries "mock" so fake results are never mistaken for
real ones. Unit tests use it, and it is a fallback if the model cannot load.

Each request appends one JSON line to REQUEST_LOG; the metrics-exporter
sidecar in the same pod tails that file (M1 report §3.2).
"""
import asyncio
import base64
import binascii
import hashlib
import io
import json
import logging
import os
import random
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import Request
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from kb_common import ApiError, create_app, request_id

MOCK_MODE = os.getenv("MOCK_MODE", "0") == "1"
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/app/model/mobilenetv2-12.onnx"))
LABELS_PATH = Path(os.getenv("LABELS_PATH", "/app/model/imagenet_classes.txt"))
REAL_MODEL_VERSION = "mobilenetv2-12-onnx"
MOCK_MODEL_VERSION = "mock-0.2.0"
REQUEST_LOG = Path(os.getenv("REQUEST_LOG", "/var/log/app/requests.jsonl"))
# Extra startup delay, to demonstrate that readiness holds traffic back (test T14).
STARTUP_DELAY_SECONDS = float(os.getenv("STARTUP_DELAY_SECONDS", "0"))
POD_NAME = os.getenv("POD_NAME", socket.gethostname())
NODE_NAME = os.getenv("NODE_NAME", "unknown")

INPUT_SIZE = (224, 224)
# torchvision's ImageNet normalisation, which this MobileNetV2 export was trained with.
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# A handful of real ImageNet class names, so mock output looks like the real thing.
MOCK_LABELS = [
    "golden retriever", "Labrador retriever", "tabby cat", "Egyptian cat", "red fox",
    "goldfish", "macaw", "monarch butterfly", "sports car", "school bus",
    "mountain bike", "espresso", "pizza", "banana", "volcano", "lakeside",
]

log = logging.getLogger("inference")


def mock_predict(image: bytes, top_k: int) -> list[dict]:
    """Deterministic fake scores: the same image always gets the same labels."""
    rng = random.Random(hashlib.sha256(image).digest())
    raw = [rng.random() ** 4 for _ in MOCK_LABELS]  # The power sharpens the distribution.
    total = sum(raw)
    ranked = sorted(zip(MOCK_LABELS, raw), key=lambda pair: pair[1], reverse=True)
    return [{"label": label, "score": round(score / total, 4)} for label, score in ranked[:top_k]]


def to_tensor(image: bytes) -> np.ndarray:
    """Decode an image into the model's input: float32, normalised, shape (1, 3, 224, 224)."""
    try:
        img = Image.open(io.BytesIO(image)).convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ApiError(400, "BAD_REQUEST", "data is not a decodable image")
    if img.size != INPUT_SIZE:
        # preprocess already sends 224x224; this only guards direct callers.
        img = ImageOps.fit(img, INPUT_SIZE, Image.Resampling.BILINEAR)
    x = np.asarray(img, dtype=np.float32) / 255.0
    x = (x - MEAN) / STD
    return x.transpose(2, 0, 1)[np.newaxis].astype(np.float32)  # HWC -> NCHW


def top_k_softmax(logits: np.ndarray, labels: list[str], k: int) -> list[dict]:
    exp = np.exp(logits - logits.max())  # Subtract the max for numerical stability.
    probs = exp / exp.sum()
    best = np.argsort(probs)[::-1][:k]
    return [{"label": labels[i], "score": round(float(probs[i]), 4)} for i in best]


class Classifier:
    """MobileNetV2 on ONNX Runtime. InferenceSession.run is safe to call from several threads."""

    def __init__(self, model_path: Path, labels_path: Path):
        import onnxruntime as ort  # Imported here so mock mode works without it.

        options = ort.SessionOptions()
        # One thread per replica, so three replicas on one node do not fight over CPU (risk R3).
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.labels = labels_path.read_text().splitlines()
        classes = self.session.get_outputs()[0].shape[-1]
        if len(self.labels) != classes:
            raise ValueError(f"{labels_path} has {len(self.labels)} labels, model outputs {classes}")

    def predict(self, image: bytes, top_k: int) -> list[dict]:
        logits = self.session.run(None, {self.input_name: to_tensor(image)})[0][0]
        return top_k_softmax(logits, self.labels, top_k)


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
    app.state.classifier = None
    loaded = True
    if not MOCK_MODE:
        started = time.perf_counter()
        try:
            app.state.classifier = await run_in_threadpool(Classifier, MODEL_PATH, LABELS_PATH)
            log.info("loaded %s in %.0f ms", MODEL_PATH.name, (time.perf_counter() - started) * 1000)
        except Exception:
            # Stay alive but not ready: the pod shows 1/2 ready in `kubectl get pods`,
            # and the Service sends it no traffic.
            log.exception("could not load model %s; staying not-ready", MODEL_PATH)
            loaded = False
    if loaded:
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        app.state.ready = True
        log.info("ready (%s, pod %s on %s)", MOCK_MODEL_VERSION if MOCK_MODE else REAL_MODEL_VERSION,
                 POD_NAME, NODE_NAME)
    yield


app = create_app("inference", lifespan=lifespan, ready=False)


class PredictRequest(BaseModel):
    data: str = Field(description="Base64-encoded 224x224 JPEG")
    topK: int = Field(default=3, ge=1, le=10)


@app.post("/predict")
async def predict(body: PredictRequest, request: Request):
    start = time.perf_counter()
    outcome, top = "error", []
    classifier: Classifier | None = request.app.state.classifier
    try:
        try:
            image = base64.b64decode(body.data, validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(400, "BAD_REQUEST", "data is not valid base64")
        if not image:
            raise ApiError(400, "BAD_REQUEST", "data is empty")
        if classifier is None:
            top = mock_predict(image, body.topK)
        else:
            # The model is CPU-bound; keep it off the event loop so probes stay responsive.
            top = await run_in_threadpool(classifier.predict, image, body.topK)
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
        "modelVersion": MOCK_MODEL_VERSION if classifier is None else REAL_MODEL_VERSION,
        "mock": classifier is None,
        "podName": POD_NAME,
        "nodeName": NODE_NAME,
    }
