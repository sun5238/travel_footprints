"""HTTP API 测试（TestClient）。"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from travel.main import create_app


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_trip_api_flow(client):
    created = client.post(
        "/api/trips",
        json={"name": "国庆成都行", "start_local": "2025-10-01T08:00:00", "tags": ["国庆"]},
    )
    assert created.status_code == 201
    trip_id = created.json()["id"]
    assert client.get(f"/api/trips/{trip_id}").json()["tags"] == ["国庆"]
    patched = client.patch(f"/api/trips/{trip_id}", json={"name": "成都国庆"})
    assert patched.json()["name"] == "成都国庆"
    assert client.delete(f"/api/trips/{trip_id}").status_code == 204
    assert client.get(f"/api/trips/{trip_id}").status_code == 404


def test_dashboard_lit_city_flow(client):
    city = client.post("/api/cities", json={"name": "成都", "lat": 30.57, "lng": 104.07}).json()
    place = client.post(
        "/api/places", json={"name": "宽窄巷子", "kind": "scene", "city_id": city["id"]}
    ).json()
    client.post(
        f"/api/places/{place['id']}/visits",
        json={"at_local": "2025-10-02T20:00:00", "rating": 4, "review": "人多但值得"},
    )
    dash = client.get("/api/dashboard").json()
    assert dash["stats"]["cities_lit"] == 1
    assert dash["lit_cities"][0]["name"] == "成都"


def test_media_upload_thumb_and_dedupe(client, photo_bytes):
    city = client.post("/api/cities", json={"name": "成都"}).json()
    place = client.post("/api/places", json={"name": "锦里", "kind": "scene", "city_id": city["id"]}).json()
    visit = client.post(f"/api/places/{place['id']}/visits", json={}).json()

    def upload() -> dict:
        resp = client.post(
            "/api/media",
            files={"file": ("shot.png", io.BytesIO(photo_bytes), "image/png")},
            data={"visit_id": str(visit["id"])},
        )
        assert resp.status_code == 201
        return resp.json()

    first = upload()
    second = upload()
    assert first["status"] == "attached"
    assert second["id"] != first["id"]
    assert len(client.get(f"/api/media?visit_id={visit['id']}").json()) == 2

    thumb_resp = client.get(first["thumb"])
    assert thumb_resp.status_code == 200
    assert thumb_resp.headers["content-type"] == "image/jpeg"


def test_restore_replaces_data(client, data_root, photo_bytes):
    city = client.post("/api/cities", json={"name": "成都"}).json()
    place = client.post("/api/places", json={"name": "宽窄巷子", "kind": "scene", "city_id": city["id"]}).json()
    client.post(f"/api/places/{place['id']}/visits", json={})

    zip_resp = client.get("/api/backup")
    assert zip_resp.status_code == 200

    fresh_root = data_root.parent / "fresh"
    app2 = create_app(fresh_root)
    with TestClient(app2) as client2:
        resp = client2.post(
            "/api/restore",
            files={"file": ("backup.zip", io.BytesIO(zip_resp.content), "application/zip")},
        )
        assert resp.status_code == 200
        assert client2.get("/api/dashboard").json()["stats"]["cities_lit"] == 1
