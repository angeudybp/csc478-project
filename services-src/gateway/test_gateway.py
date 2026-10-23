import base64
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import gateway

PROCESSED = base64.b64encode(b"\xff\xd8\xffprocessed").decode()


def jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


class FakeUpstreams:
    """Stands in for preprocess, inference and storage; tests override behaviour per service."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.stored: dict[str, bytes] = {}
        self.fail: dict[str, Exception | int] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        service = request.url.host.split("-")[0]
        self.calls.append((service, request.url.path))
        failure = self.fail.get(service)
        if isinstance(failure, Exception):
            raise failure
        if isinstance(failure, int):
            return httpx.Response(failure, json={"error": {"code": "X", "message": "boom"}})
        assert request.headers["X-Request-Id"]
        if service == "preprocess":
            return httpx.Response(200, json={"data": PROCESSED, "width": 224, "height": 224,
                                             "originalWidth": 32, "originalHeight": 32,
                                             "originalFormat": "JPEG"})
        if service == "inference":
            top = [{"label": "tabby cat", "score": 0.7}, {"label": "red fox", "score": 0.2},
                   {"label": "goldfish", "score": 0.1}]
            return httpx.Response(200, json={"label": "tabby cat", "confidence": 0.7, "topK": top,
                                             "modelVersion": "mock-0.2.0", "mock": True,
                                             "podName": "inference-a", "nodeName": "node-1"})
        if request.method == "PUT":
            self.stored[request.url.path] = request.content
            return httpx.Response(201, json={})
        if request.url.path in self.stored:
            body = self.stored[request.url.path]
            return httpx.Response(200, content=body, headers={"Content-Type": "application/json"})
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "nope"}})


@pytest.fixture
def upstreams():
    return FakeUpstreams()


@pytest.fixture
def client(upstreams):
    gateway.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(upstreams))
    return TestClient(gateway.app)  # No context manager: keep the fake client, skip the lifespan.


def upload(client, data: bytes, name="dog.jpg"):
    return client.post("/api/v1/images", files={"file": (name, data, "image/jpeg")})


def test_happy_path_runs_all_three_stages(client, upstreams):
    r = upload(client, jpeg_bytes())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "tabby cat"
    assert body["mock"] is True
    assert body["imageId"].startswith("img_")
    assert len(body["topK"]) == 3
    assert body["servedBy"]["inferencePod"] == "inference-a"
    assert set(body["timings"]) == {"preprocessMs", "inferenceMs", "storageMs", "totalMs"}
    image_id = body["imageId"]
    assert [c[0] for c in upstreams.calls] == ["preprocess", "inference", "storage", "storage", "storage"]
    assert upstreams.stored[f"/objects/{image_id}/original"] == jpeg_bytes()
    assert upstreams.stored[f"/objects/{image_id}/processed"] == base64.b64decode(PROCESSED)
    assert json.loads(upstreams.stored[f"/results/{image_id}"])["label"] == "tabby cat"


def test_uploads_are_user_uploads_unless_marked_as_tests(client, upstreams):
    first = upload(client, jpeg_bytes()).json()
    assert first["source"] == "user"
    r = client.post("/api/v1/images", files={"file": ("t.jpg", jpeg_bytes(), "image/jpeg")},
                    data={"source": "test"})
    assert r.json()["source"] == "test"
    assert json.loads(upstreams.stored[f"/results/{r.json()['imageId']}"])["source"] == "test"


def test_unknown_source_is_400(client):
    r = client.post("/api/v1/images", files={"file": ("t.jpg", jpeg_bytes(), "image/jpeg")},
                    data={"source": "admin"})
    assert r.status_code == 400


def test_result_can_be_fetched_back(client):
    image_id = upload(client, jpeg_bytes()).json()["imageId"]
    r = client.get(f"/api/v1/results/{image_id}")
    assert r.status_code == 200
    assert r.json()["imageId"] == image_id


def test_missing_file_field_is_400(client):
    r = client.post("/api/v1/images", data={"other": "x"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "EMPTY_UPLOAD"


def test_empty_file_is_400(client):
    r = upload(client, b"")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "EMPTY_UPLOAD"


def test_oversized_file_is_413_and_never_reaches_upstreams(client, upstreams):
    r = upload(client, b"\xff\xd8\xff" + b"0" * (9 * 1024 * 1024))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert upstreams.calls == []


def test_file_just_over_limit_is_413_after_reading(client):
    # Small enough to pass the Content-Length pre-check, but still over 8 MB of file data.
    r = upload(client, b"\xff\xd8\xff" + b"0" * (8 * 1024 * 1024))
    assert r.status_code == 413


@pytest.mark.parametrize("data", [b"just some text", b"GIF89a....", b"<svg xmlns='x'/>"])
def test_non_jpeg_png_is_415(client, upstreams, data):
    r = upload(client, data, name="fake.jpg")
    assert r.status_code == 415
    assert upstreams.calls == []


def test_corrupt_image_rejected_by_preprocess_is_415(client, upstreams):
    upstreams.fail["preprocess"] = 415
    r = upload(client, b"\xff\xd8\xff garbage")
    assert r.status_code == 415


def test_inference_down_is_quick_503_without_retry(client, upstreams):
    upstreams.fail["inference"] = httpx.ConnectError("refused")
    r = upload(client, jpeg_bytes())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert [c[0] for c in upstreams.calls].count("inference") == 1


def test_preprocess_connection_failure_is_retried_once(client, upstreams):
    upstreams.fail["preprocess"] = httpx.ConnectError("refused")
    r = upload(client, jpeg_bytes())
    assert r.status_code == 503
    assert [c[0] for c in upstreams.calls].count("preprocess") == 2


def test_inference_timeout_is_504(client, upstreams):
    upstreams.fail["inference"] = httpx.ReadTimeout("slow")
    r = upload(client, jpeg_bytes())
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "UPSTREAM_TIMEOUT"


def test_upstream_500_is_502(client, upstreams):
    upstreams.fail["inference"] = 500
    assert upload(client, jpeg_bytes()).status_code == 502


def test_unknown_result_is_404(client):
    r = client.get("/api/v1/results/img_doesnotexist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_request_id_is_returned(client):
    r = upload(client, b"text", name="a.txt")
    assert r.headers["X-Request-Id"] == r.json()["requestId"]


def test_ui_page_is_served_from_the_gateway(client, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    monkeypatch.setattr(gateway, "UI_DIR", tmp_path)
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "root" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_missing_ui_build_is_a_clean_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "UI_DIR", tmp_path / "nothing")
    r = client.get("/")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
