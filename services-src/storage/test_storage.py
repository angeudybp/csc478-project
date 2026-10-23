import pytest
from fastapi.testclient import TestClient

import storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage._object_paths.clear()
    with TestClient(storage.app) as c:
        yield c


def test_object_round_trip_uses_dated_layout(client, tmp_path):
    r = client.put("/objects/img_ABC123/original", content=b"\xff\xd8\xffjpeg",
                   headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 201
    assert r.json()["path"].startswith("originals/")
    assert r.json()["path"].endswith("/img_ABC123.jpg")

    r = client.get("/objects/img_ABC123/original")
    assert r.status_code == 200
    assert r.content == b"\xff\xd8\xffjpeg"
    assert r.headers["content-type"] == "image/jpeg"


def test_object_is_found_after_cache_is_lost(client):
    client.put("/objects/img_X1/processed", content=b"jpg", headers={"Content-Type": "image/jpeg"})
    storage._object_paths.clear()  # Simulates a restart with the same data volume.
    assert client.get("/objects/img_X1/processed").content == b"jpg"


def test_result_round_trip_and_overwrite(client):
    assert client.put("/results/img_R1", json={"label": "cat", "createdAt": "t1"}).status_code == 201
    assert client.put("/results/img_R1", json={"label": "dog", "createdAt": "t1"}).status_code == 200
    r = client.get("/results/img_R1")
    assert r.json() == {"label": "dog", "createdAt": "t1", "imageId": "img_R1"}


def test_list_is_newest_first_without_duplicates(client):
    for i in range(3):
        client.put(f"/results/img_L{i}", json={"label": str(i)})
    client.put("/results/img_L0", json={"label": "again"})
    ids = [r["imageId"] for r in client.get("/results?limit=10").json()["results"]]
    assert ids == ["img_L2", "img_L1", "img_L0"]
    assert len(client.get("/results?limit=2").json()["results"]) == 2


def test_unknown_ids_are_404(client):
    assert client.get("/results/img_nope").status_code == 404
    assert client.get("/objects/img_nope/original").status_code == 404


@pytest.mark.parametrize("bad_id", ["../etc", "img_../x", "notanid", "img_" + "a" * 41])
def test_invalid_ids_are_rejected(client, bad_id):
    assert client.get(f"/results/{bad_id}").status_code in (400, 404)
    r = client.put(f"/objects/{bad_id}/original", content=b"x", headers={"Content-Type": "image/png"})
    assert r.status_code in (400, 404)


def test_bad_variant_and_content_type(client):
    assert client.put("/objects/img_V/thumbnail", content=b"x",
                      headers={"Content-Type": "image/png"}).status_code == 400
    assert client.put("/objects/img_V/original", content=b"x",
                      headers={"Content-Type": "image/gif"}).status_code == 415
