import base64
import json

import pytest
from fastapi.testclient import TestClient

import inference


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "REQUEST_LOG", tmp_path / "requests.jsonl")
    with TestClient(inference.app) as c:  # The context manager runs the lifespan (readiness).
        yield c


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_mock_prediction_is_deterministic():
    assert inference.mock_predict(b"same bytes", 3) == inference.mock_predict(b"same bytes", 3)
    assert inference.mock_predict(b"a", 3) != inference.mock_predict(b"b", 3)


def test_scores_are_sorted_probabilities():
    top = inference.mock_predict(b"img", len(inference.LABELS))
    scores = [t["score"] for t in top]
    assert scores == sorted(scores, reverse=True)
    assert abs(sum(scores) - 1) < 0.01


def test_predict_returns_top_k_and_mock_flag(client):
    r = client.post("/predict", json={"data": b64(b"fake jpeg"), "topK": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] is True
    assert len(body["topK"]) == 3
    assert body["label"] == body["topK"][0]["label"]
    assert body["podName"]


def test_ready_after_startup(client):
    assert client.get("/readyz").status_code == 200


def test_each_request_is_logged_for_the_sidecar(client):
    client.post("/predict", json={"data": b64(b"one")}, headers={"X-Request-Id": "r1"})
    client.post("/predict", json={"data": "%%%not-base64%%%"}, headers={"X-Request-Id": "r2"})
    lines = [json.loads(l) for l in inference.REQUEST_LOG.read_text().splitlines()]
    assert [(l["requestId"], l["outcome"]) for l in lines] == [("r1", "ok"), ("r2", "error")]
    assert all(l["latencyMs"] >= 0 for l in lines)


def test_bad_base64_is_400(client):
    r = client.post("/predict", json={"data": "%%%"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"


def test_top_k_out_of_range_is_400(client):
    r = client.post("/predict", json={"data": b64(b"x"), "topK": 50})
    assert r.status_code == 400
