import json
import threading
import time

from exporter import Metrics, percentile, tail


def line(latency, outcome="ok"):
    return json.dumps({"latencyMs": latency, "outcome": outcome})


def test_percentile_nearest_rank():
    values = list(range(1, 101))
    assert percentile(values, 0.5) == 50
    assert percentile(values, 0.95) == 95
    assert percentile([], 0.5) == 0.0
    assert percentile([7], 0.95) == 7


def test_counts_requests_errors_and_latency():
    m = Metrics()
    for latency in (10, 20, 30):
        m.ingest(line(latency))
    m.ingest(line(40, outcome="error"))
    m.ingest("{not json")
    out = m.render(pod="inference-abc")
    assert 'inference_requests_total{pod="inference-abc"} 4' in out
    assert 'inference_request_errors_total{pod="inference-abc"} 1' in out
    assert 'inference_request_latency_ms_sum{pod="inference-abc"} 100.000' in out


def test_latency_window_is_bounded():
    m = Metrics(window=2)
    for latency in (1000, 1, 1):
        m.ingest(line(latency))
    assert percentile(m.latencies, 0.95) == 1
    assert m.requests == 3


def test_tail_follows_appends_and_waits_for_file(tmp_path):
    log = tmp_path / "requests.jsonl"
    m, stop = Metrics(), threading.Event()
    worker = threading.Thread(target=tail, args=(log, m, stop), daemon=True)
    worker.start()
    try:
        time.sleep(0.2)
        log.write_text(line(5) + "\n" + '{"latencyMs": 6')  # Second line is still being written.
        deadline = time.time() + 3
        while m.requests < 1 and time.time() < deadline:
            time.sleep(0.05)
        assert m.requests == 1
        with log.open("a") as f:
            f.write(', "outcome": "ok"}\n')
        deadline = time.time() + 3
        while m.requests < 2 and time.time() < deadline:
            time.sleep(0.05)
        assert m.requests == 2
    finally:
        stop.set()
        worker.join(timeout=2)
