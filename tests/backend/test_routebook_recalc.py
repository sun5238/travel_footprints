"""S3: 途经点变更 → 重算接线（Archive.recalc_routebook + API）。

低成本路网图由 conftest.greenway_graph 提供；无图时 recalc 明确报错。
"""

from __future__ import annotations

import pytest

from travel.store import Archive

S = {"name": "S", "lat": 30.0, "lng": 100.0, "pos_kind": "exact"}
R = {"name": "R", "lat": 30.0, "lng": 100.015, "pos_kind": "exact"}
G1 = {"name": "G1", "lat": 30.0, "lng": 100.01, "pos_kind": "exact"}
E = {"name": "E", "lat": 30.0, "lng": 100.03, "pos_kind": "exact"}


def _latlngs(book, key="geometry"):
    geojson = book[key]["geojson"]
    assert geojson is not None
    return [(round(c[1], 5), round(c[0], 5)) for c in geojson["coordinates"]]


def test_recalc_engine_line_defaults(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook(
        "骑行", mode="cycling", preset="balanced", points=[S, E]
    )
    assert book["geometry"]["source"] == "engine" and book["geometry"]["geojson"] is None
    assert book["mileage_km"] is None

    recalced = archive_with_graph.recalc_routebook(book["id"])
    assert recalced["geometry"]["source"] == "engine"
    assert recalced["geometry"]["geojson"]["type"] == "LineString"
    assert _latlngs(recalced) == [(30.0, 100.0), (30.0, 100.015), (30.0, 100.03)]
    assert recalced["mileage_km"] == 2.5


def test_recalc_responds_to_preset_change(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook(
        "骑行", mode="cycling", preset="balanced", points=[S, E]
    )
    archive_with_graph.update_routebook(book["id"], {"preset": "greenway"})
    recalced = archive_with_graph.recalc_routebook(book["id"])
    # 绿道档位切换 → 重算换线（走更长但更绿的绿道）
    assert _latlngs(recalced) == [
        (30.0, 100.0), (30.0, 100.01), (30.0, 100.02), (30.0, 100.03),
    ]


def test_recalc_with_via_point_wires_through(archive_with_graph: Archive):
    # 途经点 G1（在绿道线上）：重算后线必经该点，里程随之
    book = archive_with_graph.create_routebook(
        "骑行", mode="cycling", preset="balanced", points=[S, G1, E]
    )
    recalced = archive_with_graph.recalc_routebook(book["id"])
    assert (30.0, 100.01) in _latlngs(recalced)
    assert recalced["mileage_km"] == 9.0


def test_recalc_replace_points_then_recalc(archive_with_graph: Archive):
    # 增删途经点后（整表替换）重算：新线按新点生成
    book = archive_with_graph.create_routebook(
        "骑行", mode="cycling", preset="balanced", points=[S, E]
    )
    archive_with_graph.update_routebook(book["id"], {"points": [S, G1, E]})
    recalced = archive_with_graph.recalc_routebook(book["id"])
    assert _latlngs(recalced) == [
        (30.0, 100.0), (30.0, 100.01), (30.0, 100.02), (30.0, 100.03),
    ]


def test_recalc_unroutable_raises(archive_with_graph: Archive):
    # 只有一个有坐标点 → 无法成线
    book = archive_with_graph.create_routebook(
        "x",
        points=[S, {"name": "无坐标", "lat": None, "lng": None, "pos_kind": "none"}],
    )
    with pytest.raises(ValueError, match="无法生成路线"):
        archive_with_graph.recalc_routebook(book["id"])


def test_recalc_requires_graph(archive: Archive):
    book = archive.create_routebook("x", points=[S, E])
    with pytest.raises(ValueError, match="未配置路网"):
        archive.recalc_routebook(book["id"])


def test_routebook_recalc_api_happy_path(client_with_graph):
    book = client_with_graph.post(
        "/api/routebooks",
        json={"name": "骑行", "mode": "cycling", "preset": "balanced",
              "points": [S, E]},
    ).json()
    resp = client_with_graph.post(f"/api/routebooks/{book['id']}/recalc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["geometry"]["source"] == "engine"
    assert body["mileage_km"] == 2.5


def test_routebook_recalc_api_without_graph_400(client):
    book = client.post(
        "/api/routebooks", json={"name": "x", "points": [S, E]}
    ).json()
    resp = client.post(f"/api/routebooks/{book['id']}/recalc")
    assert resp.status_code == 400
    assert "未配置路网" in resp.json()["detail"]


def test_routebook_recalc_missing_400(client):
    resp = client.post("/api/routebooks/999999/recalc")
    assert resp.status_code == 400
    assert "路书不存在" in resp.json()["detail"]