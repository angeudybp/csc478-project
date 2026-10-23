import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

from preprocess import app

client = TestClient(app)


def make_image(fmt: str, size=(640, 480), color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def test_resizes_jpeg_to_224():
    r = client.post("/preprocess", content=make_image("JPEG"))
    assert r.status_code == 200
    body = r.json()
    assert (body["originalWidth"], body["originalHeight"]) == (640, 480)
    out = Image.open(io.BytesIO(base64.b64decode(body["data"])))
    assert out.format == "JPEG"
    assert out.size == (224, 224)


def test_png_is_accepted_and_converted_to_jpeg():
    r = client.post("/preprocess", content=make_image("PNG", size=(100, 300)))
    assert r.status_code == 200
    assert r.json()["originalFormat"] == "PNG"


def test_exif_is_stripped():
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    Image.new("RGB", (300, 300)).save(buf, "JPEG", exif=exif)
    r = client.post("/preprocess", content=buf.getvalue())
    out = base64.b64decode(r.json()["data"])
    assert b"SecretCameraMaker" not in out


def test_text_file_is_415():
    r = client.post("/preprocess", content=b"definitely not an image")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_gif_is_415():
    r = client.post("/preprocess", content=make_image("GIF"))
    assert r.status_code == 415


def test_empty_body_is_400():
    r = client.post("/preprocess", content=b"")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "EMPTY_UPLOAD"


def test_request_id_is_echoed():
    r = client.post("/preprocess", content=b"x", headers={"X-Request-Id": "abc123"})
    assert r.headers["X-Request-Id"] == "abc123"
    assert r.json()["requestId"] == "abc123"
