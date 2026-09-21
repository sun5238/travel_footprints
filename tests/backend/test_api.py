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


def test_import_parse_returns_draft(client):
    resp = client.post("/api/import/parse", json={"text": "# 国庆\n@2026-10-01 ~ 2026-10-07\n@成都"})
    assert resp.status_code == 200
    draft = resp.json()
    assert draft["title"] == "国庆"
    assert draft["trip_range"]["start_date"] == "2026-10-01"
    assert [c["name"] for c in draft["cities"]] == ["成都"]


def test_visit_patch_roundtrip(client):
    place = client.post("/api/places", json={"name": "宽窄巷子", "kind": "scene"}).json()
    visit = client.post(
        f"/api/places/{place['id']}/visits",
        json={"at_local": "2026-10-01T14:20:00", "rating": 4, "label": "古镇", "companions": ["小明"]},
    ).json()
    assert visit["label"] == "古镇"
    assert visit["companions"] == ["小明"]

    original_local = visit["at"]["local"]
    patched = client.patch(
        f"/api/visits/{visit['id']}",
        json={"rating": 5, "label": "爬山", "pos_kind": "point", "review": "不错"},
    ).json()
    assert patched["rating"] == 5
    assert patched["label"] == "爬山"
    assert patched["pos_kind"] == "point"
    assert patched["at"]["local"] == original_local  # 未动时间


def test_visit_patch_invalid_rating_422(client):
    # rating 由 Pydantic ge/le 校验（与 VisitIn 同一口径），越界返回 422
    place = client.post("/api/places", json={"name": "长江索道", "kind": "scene"}).json()
    visit = client.post(f"/api/places/{place['id']}/visits", json={}).json()
    resp = client.patch(f"/api/visits/{visit['id']}", json={"rating": 9})
    assert resp.status_code == 422


def test_leg_patch_roundtrip(client):
    trip = client.post("/api/trips", json={"name": "成都行"}).json()
    leg = client.post(
        f"/api/trips/{trip['id']}/legs",
        json={"from_text": "重庆北", "to_text": "成都东", "mode": "高铁", "price": 154.5},
    ).json()
    assert leg["price"] == 154.5
    patched = client.patch(
        f"/api/legs/{leg['id']}", json={"mode": "动车", "price": 126.0, "note": "转到东站"}
    ).json()
    assert patched["mode"] == "动车"
    assert patched["price"] == 126.0
    assert patched["note"] == "转到东站"


def test_media_batch_unassign_and_delete(client, photo_bytes):
    city = client.post("/api/cities", json={"name": "成都"}).json()
    place = client.post("/api/places", json={"name": "锦里", "kind": "scene", "city_id": city["id"]}).json()
    visit = client.post(f"/api/places/{place['id']}/visits", json={}).json()

    ids = []
    for i in range(3):
        resp = client.post(
            "/api/media",
            files={"file": (f"shot{i}.png", io.BytesIO(photo_bytes), "image/png")},
            data={"visit_id": str(visit["id"])},
        )
        ids.append(resp.json()["id"])
    assert all(m["status"] == "attached" for m in client.get("/api/media").json())

    # unassign：解绑回 pending，不删文件
    resp = client.patch("/api/media/batch", json={"ids": ids[:2], "action": "unassign"})
    assert resp.status_code == 200
    rows = client.get("/api/media").json()
    detached = [m for m in rows if m["id"] in ids[:2]]
    assert all(m["status"] == "pending" and m["visit_id"] is None for m in detached)

    # delete：删除剩余 1 条
    client.patch("/api/media/batch", json={"ids": [ids[2]], "action": "delete"})
    after = {m["id"] for m in client.get("/api/media").json()}
    assert ids[2] not in after and ids[0] in after


def test_media_batch_unknown_action_400(client):
    resp = client.patch("/api/media/batch", json={"ids": [1], "action": "explode"})
    assert resp.status_code == 422  # Literal 校验层


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
