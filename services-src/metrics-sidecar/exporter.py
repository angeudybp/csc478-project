"""metrics-exporter: sidecar that turns the inference request log into Prometheus metrics.

It shares an emptyDir with the inference container, tails requests.jsonl, and
serves per-replica request count, error count and p50/p95 latency on :9100
(M1 report §3.2). Metrics live in memory and reset when the pod restarts.
"""
import json
import logging
import math
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi.responses import PlainTextResponse

from kb_common import create_app

REQUEST_LOG = Path(os.getenv("REQUEST_LOG", "/var/log/app/requests.jsonl"))
POD_NAME = os.getenv("POD_NAME", "unknown")
# Percentiles are computed over the most recent requests only, so memory stays bounded.
LATENCY_WINDOW = int(os.getenv("LATENCY_WINDOW", "1000"))
POLL_SECONDS = 0.5

log = logging.getLogger("metrics-exporter")


def percentile(values, q: float) -> float:
    """Nearest-rank percentile; 0.0 for no data."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(q * len(ordered))))
    return ordered[rank - 1]


class Metrics:
    def __init__(self, window: int = LATENCY_WINDOW):
        self._lock = threading.Lock()
        self.requests = 0
        self.errors = 0
        self.latency_sum = 0.0
        self.latencies = deque(maxlen=window)

    def ingest(self, line: str) -> None:
        try:
            entry = json.loads(line)
            latency = float(entry["latencyMs"])
        except (ValueError, KeyError, TypeError):
            return  # Skip partial or malformed lines rather than crash the exporter.
        with self._lock:
            self.requests += 1
            if entry.get("outcome") != "ok":
                self.errors += 1
            self.latency_sum += latency
            self.latencies.append(latency)

    def render(self, pod: str = POD_NAME) -> str:
        with self._lock:
            label = f'pod="{pod}"'
            p50 = percentile(self.latencies, 0.50)
            p95 = percentile(self.latencies, 0.95)
            return "\n".join([
                "# HELP inference_requests_total Prediction requests handled by this replica.",
                "# TYPE inference_requests_total counter",
                f"inference_requests_total{{{label}}} {self.requests}",
                "# HELP inference_request_errors_total Prediction requests that failed.",
                "# TYPE inference_request_errors_total counter",
                f"inference_request_errors_total{{{label}}} {self.errors}",
                "# HELP inference_request_latency_ms Prediction latency in milliseconds.",
                "# TYPE inference_request_latency_ms summary",
                f'inference_request_latency_ms{{{label},quantile="0.5"}} {p50:.3f}',
                f'inference_request_latency_ms{{{label},quantile="0.95"}} {p95:.3f}',
                f"inference_request_latency_ms_sum{{{label}}} {self.latency_sum:.3f}",
                f"inference_request_latency_ms_count{{{label}}} {self.requests}",
                "",
            ])


def tail(path: Path, metrics: Metrics, stop: threading.Event) -> None:
    """Follow ``path`` like ``tail -F``: wait for it to appear and reopen it if it is truncated."""
    position, pending = 0, ""
    while not stop.is_set():
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            stop.wait(POLL_SECONDS)
            continue
        if size < position:
            position, pending = 0, ""  # File was truncated or replaced.
        if size > position:
            with path.open("r") as f:
                f.seek(position)
                chunk = f.read()
                position = f.tell()
            pending += chunk
            *lines, pending = pending.split("\n")  # Keep a trailing partial line for next time.
            for line in lines:
                if line.strip():
                    metrics.ingest(line)
        stop.wait(POLL_SECONDS)


metrics = Metrics()


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    worker = threading.Thread(target=tail, args=(REQUEST_LOG, metrics, stop), daemon=True)
    worker.start()
    log.info("tailing %s for pod %s", REQUEST_LOG, POD_NAME)
    yield
    stop.set()
    worker.join(timeout=2)


app = create_app("metrics-exporter", lifespan=lifespan)


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")
