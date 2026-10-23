import base64
import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import inference


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "REQUEST_LOG", tmp_path / "requests.jsonl")
    monkeypatch.setattr(inference, "MOCK_MODE", True)
    with TestClient(inference.app) as c:  # The context manager runs the lifespan (readiness).
        yield c


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def jpeg(size=(224, 224), color=(120, 40, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


class FakeSession:
    """Stands in for onnxruntime.InferenceSession: returns fixed logits and records the input."""

    def __init__(self, logits):
        self.logits = np.asarray(logits, dtype=np.float32)
        self.seen = None

    def run(self, _outputs, feeds):
        self.seen = feeds["input"]
        return [self.logits[np.newaxis]]


def fake_classifier(logits, labels):
    clf = inference.Classifier.__new__(inference.Classifier)  # Skip loading a real model.
    clf.session, clf.input_name, clf.labels = FakeSession(logits), "input", labels
    return clf


# --- mock mode ----------------------------------------------------------------------------

def test_mock_prediction_is_deterministic():
    assert inference.mock_predict(b"same bytes", 3) == inference.mock_predict(b"same bytes", 3)
    assert inference.mock_predict(b"a", 3) != inference.mock_predict(b"b", 3)


def test_mock_scores_are_sorted_probabilities():
    top = inference.mock_predict(b"img", len(inference.MOCK_LABELS))
    scores = [t["score"] for t in top]
    assert scores == sorted(scores, reverse=True)
    assert abs(sum(scores) - 1) < 0.01


def test_predict_in_mock_mode_is_flagged(client):
    r = client.post("/predict", json={"data": b64(b"fake jpeg"), "topK": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] is True
    assert body["modelVersion"] == inference.MOCK_MODEL_VERSION
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


# --- real model path ----------------------------------------------------------------------

def test_to_tensor_shape_and_normalisation():
    x = inference.to_tensor(jpeg(color=(255, 255, 255)))
    assert x.shape == (1, 3, 224, 224)
    assert x.dtype == np.float32
    # White pixels normalise to (1 - mean) / std per channel (JPEG may shift values slightly).
    expected = (1 - inference.MEAN) / inference.STD
    assert np.allclose(x[0, :, 100, 100], expected, atol=0.05)


def test_to_tensor_resizes_other_sizes():
    assert inference.to_tensor(jpeg(size=(640, 480))).shape == (1, 3, 224, 224)


def test_to_tensor_rejects_non_images():
    with pytest.raises(inference.ApiError) as err:
        inference.to_tensor(b"not an image")
    assert err.value.status == 400


def test_top_k_softmax_ranks_and_normalises():
    top = inference.top_k_softmax(np.array([0.0, 3.0, 1.0, 2.0]), ["a", "b", "c", "d"], 3)
    assert [t["label"] for t in top] == ["b", "d", "c"]
    probs = np.exp([0.0, 3.0, 1.0, 2.0]) / np.exp([0.0, 3.0, 1.0, 2.0]).sum()
    assert top[0]["score"] == round(float(probs[1]), 4)


def test_classifier_feeds_model_and_maps_labels():
    clf = fake_classifier([0.1, 5.0, 0.2], ["cat", "dog", "fox"])
    top = clf.predict(jpeg(), 2)
    assert [t["label"] for t in top] == ["dog", "fox"]
    assert clf.session.seen.shape == (1, 3, 224, 224)


def test_predict_uses_the_real_model_when_loaded(client):
    client.app.state.classifier = fake_classifier([0.0, 9.0], ["not it", "Samoyed"])
    r = client.post("/predict", json={"data": b64(jpeg()), "topK": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Samoyed"
    assert body["mock"] is False
    assert body["modelVersion"] == inference.REAL_MODEL_VERSION


def test_missing_model_keeps_pod_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "REQUEST_LOG", tmp_path / "requests.jsonl")
    monkeypatch.setattr(inference, "MOCK_MODE", False)
    monkeypatch.setattr(inference, "MODEL_PATH", tmp_path / "missing.onnx")
    inference.app.state.ready = False
    with TestClient(inference.app) as c:
        assert c.get("/healthz").status_code == 200
        r = c.get("/readyz")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "NOT_READY"
