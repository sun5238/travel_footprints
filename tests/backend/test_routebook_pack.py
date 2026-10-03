"""S6: 路书 zip 导出/导入（manifest.json + route.geojson）、同名不覆盖。"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from travel.routebook_pack import read_routebook_zip, write_routebook_zip
from travel.store import Archive

S = {"name": "S", "lat": 30.0, "lng": 100.0, "pos_kind": "exact"}
E = {"name": "E", "lat": 30.0, "lng": 100.03, "pos_kind": "exact"}
STOP = {"name": "映秀充电站", "lat": 31.05, "lng": 103.56, "pos_kind": "exact",
        "stop_type": "charging", "stop_note": "国网 8 桩"}


def _book_dict() -> dict:
    return {
        "id": 1,
        "name": "成都骑行",
        "mode": "cycling",
        "preset": "greenway",
        "mileage_km": 12.3,
        "mileage_manual": False,
        "geometry": {
            "source": "engine",
            "geojson": {"type": "LineString", "coordinates": [[100.0, 30.0], [103.0, 30.0]]},
        },
        "created_epoch": 1.0,
        "updated_epoch": 2.0,
        "points": [
            {"id": 1, "name": "S", "lat": 30.0, "lng": 100.0, "pos_kind": "exact",
             "stop_type": None, "stop_name": "", "stop_note": ""},
            {"id": 2, "name": "E", "lat": 30.0, "lng": 103.0, "pos_kind": "exact",
             "stop_type": "scene", "stop_name": "某景", "stop_note": "desc"},
        ],
        "stops": [
            {"id": 1, "name": "充", "lat": 30.5, "lng": 101.0, "pos_kind": "exact",
             "stop_type": "charging", "stop_note": "8 桩"},
        ],
    }


# ---------- 纯函数 io ----------

def test_write_read_roundtrip(tmp_path):
    dest = tmp_path / "rb.zip"
    write_routebook_zip(_book_dict(), dest)
    data = read_routebook_zip(dest)
    assert data["name"] == "成都骑行"
    assert data["mode"] == "cycling"
    assert data["preset"] == "greenway"
    assert data["mileage_km"] == 12.3 and data["mileage_manual"] is False
    assert data["geometry_json"] is not None
    assert data["points"][1]["stop_type"] == "scene"
    assert data["stops"][0]["stop_type"] == "charging"


def test_zip_layout(tmp_path):
    dest = tmp_path / "rb.zip"
    write_routebook_zip(_book_dict(), dest)
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        assert "manifest.json" in names and "route.geojson" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["kind"] == "routebook"
        assert b"LineString" in zf.read("route.geojson")


def test_write_without_line_omits_route_geojson(tmp_path):
    d = _book_dict()
    d["geometry"] = {"source": "engine", "geojson": None}
    dest = tmp_path / "rb.zip"
    write_routebook_zip(d, dest)
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
    assert "manifest.json" in names and "route.geojson" not in names


def test_read_rejects_missing_manifest(tmp_path):
    dest = tmp_path / "bad.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("x.txt", "hello")
    with pytest.raises(ValueError, match="manifest"):
        read_routebook_zip(dest)


def test_read_rejects_foreign_kind(tmp_path):
    dest = tmp_path / "bad.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"kind": "memo", "name": "x"}))
    with pytest.raises(ValueError, match="路书包"):
        read_routebook_zip(dest)


def test_read_rejects_missing_name(tmp_path):
    dest = tmp_path / "bad.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"kind": "routebook"}))
    with pytest.raises(ValueError, match="名称"):
        read_routebook_zip(dest)


# ---------- store 导出/导入 ----------

def test_export_import_roundtrip_new_book(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook(
        "骑行", mode="cycling", preset="greenway", points=[S, E], stops=[STOP]
    )
    archive_with_graph.recalc_routebook(book["id"])
    dest = archive_with_graph.export_routebook(book["id"])
    created = archive_with_graph.import_routebook(dest)
    assert created["id"] != book["id"]
    assert created["name"] == "骑行"
    assert created["mode"] == "cycling" and created["preset"] == "greenway"
    assert created["geometry"]["source"] == "engine"
    assert created["geometry"]["geojson"] is not None
    # greenway 档重算取绿道线（9km 长线），导入后里程精确还原
    assert created["mileage_km"] == 9.0 and created["mileage_manual"] is False
    assert len(created["stops"]) == 1 and created["stops"][0]["stop_type"] == "charging"
    assert len(archive_with_graph.list_routebooks()) == 2


def test_import_same_name_does_not_overwrite(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook(
        "骑行", mode="cycling", preset="balanced", points=[S, E]
    )
    archive_with_graph.recalc_routebook(book["id"])
    dest = archive_with_graph.export_routebook(book["id"])
    a = archive_with_graph.import_routebook(dest)
    b = archive_with_graph.import_routebook(dest)
    assert a["id"] != b["id"] and a["name"] == b["name"]
    assert len(archive_with_graph.list_routebooks()) == 3


def test_import_rejects_invalid_mode(archive_with_graph: Archive, tmp_path):
    dest = tmp_path / "bad.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"kind": "routebook", "name": "x", "mode": "flying"}))
    with pytest.raises(ValueError, match="未知模式"):
        archive_with_graph.import_routebook(dest)


# ---------- API ----------

def test_export_api_zip(client_with_graph):
    book = client_with_graph.post(
        "/api/routebooks", json={"name": "骑行", "mode": "cycling", "points": [S, E]}
    ).json()
    client_with_graph.post(f"/api/routebooks/{book['id']}/recalc")
    resp = client_with_graph.get(f"/api/routebooks/{book['id']}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
    assert "manifest.json" in names


def test_export_api_missing_400(client):
    resp = client.get("/api/routebooks/999999/export")
    assert resp.status_code == 400
    assert "路书不存在" in resp.json()["detail"]


def test_import_api_creates_book(client_with_graph):
    book = client_with_graph.post(
        "/api/routebooks", json={"name": "骑行", "mode": "cycling", "points": [S, E]}
    ).json()
    client_with_graph.post(f"/api/routebooks/{book['id']}/recalc")
    zip_bytes = client_with_graph.get(f"/api/routebooks/{book['id']}/export").content
    resp = client_with_graph.post(
        "/api/routebooks/import", files={"file": ("r.zip", zip_bytes, "application/zip")}
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "骑行"
    assert len(client_with_graph.get("/api/routebooks").json()) == 2