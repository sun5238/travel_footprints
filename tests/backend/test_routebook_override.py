"""S4: 覆盖几何保有 + 里程手动改（重算不吞用户输入）。"""

from __future__ import annotations

import json

import pytest

from travel.store import Archive

S = {"name": "S", "lat": 30.0, "lng": 100.0, "pos_kind": "exact"}
E = {"name": "E", "lat": 30.0, "lng": 100.03, "pos_kind": "exact"}

DRAWN = {"type": "LineString", "coordinates": [[100.0, 30.0], [100.06, 30.0]]}


def test_override_geometry_set_and_present(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook("x", points=[S, E])
    updated = archive_with_graph.update_routebook(
        book["id"],
        {"geometry_source": "override", "geometry_json": json.dumps(DRAWN)},
    )
    assert updated["geometry"]["source"] == "override"
    assert updated["geometry"]["geojson"] == DRAWN
    got = archive_with_graph.get_routebook(book["id"])
    assert got["geometry"]["source"] == "override"
    assert got["geometry"]["geojson"]["type"] == "LineString"


def test_recalc_refuses_to_clobber_override(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook("x", points=[S, E])
    archive_with_graph.update_routebook(
        book["id"],
        {"geometry_source": "override", "geometry_json": json.dumps(DRAWN)},
    )
    with pytest.raises(ValueError, match="覆盖"):
        archive_with_graph.recalc_routebook(book["id"])
    got = archive_with_graph.get_routebook(book["id"])
    assert got["geometry"]["source"] == "override"
    assert got["geometry"]["geojson"] == DRAWN


def test_switch_back_to_engine_then_recalc(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook(
        "骑行", mode="cycling", preset="balanced", points=[S, E]
    )
    archive_with_graph.update_routebook(
        book["id"],
        {"geometry_source": "override", "geometry_json": json.dumps(DRAWN)},
    )
    archive_with_graph.update_routebook(book["id"], {"geometry_source": "engine"})
    recalced = archive_with_graph.recalc_routebook(book["id"])
    assert recalced["geometry"]["source"] == "engine"
    assert recalced["mileage_km"] == 2.5
    coords = [(c[1], c[0]) for c in recalced["geometry"]["geojson"]["coordinates"]]
    assert coords == [(30.0, 100.0), (30.0, 100.015), (30.0, 100.03)]


def test_manual_mileage_survives_recalc(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook("x", points=[S, E])
    archive_with_graph.update_routebook(book["id"], {"mileage_km": 88.5})
    recalced = archive_with_graph.recalc_routebook(book["id"])
    assert recalced["mileage_km"] == 88.5
    assert recalced["mileage_manual"] is True


def test_invalid_geometry_source_raises(archive_with_graph: Archive):
    book = archive_with_graph.create_routebook("x")
    with pytest.raises(ValueError, match="未知几何来源"):
        archive_with_graph.update_routebook(book["id"], {"geometry_source": "silly"})