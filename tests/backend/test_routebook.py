"""RouteBook store 测试：路书 CRUD 往返、默认值、字段校验、点/停靠替换、删级联。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from travel.models import RoutePoint, RouteStop
from travel.store import Archive

A_POINT = {
    "name": "成都", "lat": 30.65, "lng": 104.06, "pos_kind": "exact",
    "stop_type": None, "stop_name": "", "stop_note": "",
}
B_POINT = {
    "name": "都江堰", "lat": 30.99, "lng": 103.62, "pos_kind": "exact",
    "stop_type": "scene", "stop_name": "都江堰景区", "stop_note": "离堆公园入口",
}
C_POINT = {
    "name": "四姑娘山", "lat": 31.2, "lng": 102.9, "pos_kind": "city",
    "stop_type": "lodging", "stop_name": "日隆镇民宿", "stop_note": "",
}
A_STOP = {
    "name": "映秀充电站", "lat": 31.05, "lng": 103.56, "pos_kind": "exact",
    "stop_type": "charging", "stop_note": "国网 8 桩",
}
B_STOP = {
    "name": "卧龙观景台", "lat": 30.99, "lng": 103.17, "pos_kind": "exact",
    "stop_type": "scene", "stop_note": "",
}


def test_create_routebook_roundtrip(archive: Archive):
    book = archive.create_routebook(
        "成都骑行路书", mode="cycling", points=[A_POINT, B_POINT, C_POINT], stops=[A_STOP, B_STOP]
    )
    assert book["name"] == "成都骑行路书"
    assert book["mode"] == "cycling"
    assert len(book["points"]) == 3 and len(book["stops"]) == 2

    got = archive.get_routebook(book["id"])
    assert got is not None
    assert got["name"] == "成都骑行路书"
    assert got["points"][1]["stop_type"] == "scene"
    assert got["points"][1]["stop_name"] == "都江堰景区"
    assert got["stops"][0]["stop_type"] == "charging"
    assert [p["id"] for p in got["points"]] == [p["id"] for p in book["points"]]

    listed = archive.list_routebooks()
    assert len(listed) == 1 and listed[0]["id"] == book["id"]
    # 列表视图不携带嵌套点集（详情才有），但共享头部字段
    assert set(listed[0]) == {
        "id", "name", "mode", "preset", "mileage_km", "mileage_manual", "geometry",
        "created_epoch", "updated_epoch",
    }


def test_create_routebook_defaults(archive: Archive):
    book = archive.create_routebook("空路书")
    assert book["mode"] == "driving"
    assert book["preset"] == "balanced"
    assert book["mileage_km"] is None
    assert book["mileage_manual"] is False
    assert book["geometry"] == {"source": "engine", "geojson": None}
    assert book["points"] == [] and book["stops"] == []


def test_create_routebook_invalid_mode(archive: Archive):
    with pytest.raises(ValueError, match="未知模式"):
        archive.create_routebook("x", mode="flying")


@pytest.mark.parametrize("field", ["pos_kind", "stop_type"])
def test_create_routebook_invalid_point_value(archive: Archive, field: str):
    bad = dict(A_POINT)
    bad[field] = "void"
    with pytest.raises(ValueError, match="未知"):
        archive.create_routebook("x", points=[bad])


def test_update_routebook_fields(archive: Archive):
    book = archive.create_routebook("旧名", mode="driving")
    updated = archive.update_routebook(
        book["id"], {"name": "新名", "preset": "scenic", "mileage_km": 88.5}
    )
    assert updated["name"] == "新名" and updated["preset"] == "scenic"
    assert updated["mileage_km"] == 88.5 and updated["mileage_manual"] is True
    assert archive.get_routebook(book["id"])["name"] == "新名"


def test_update_routebook_replace_points_and_stops(archive: Archive):
    book = archive.create_routebook("x", points=[A_POINT, B_POINT])
    updated = archive.update_routebook(book["id"], {"points": [C_POINT], "stops": [A_STOP]})
    assert len(updated["points"]) == 1 and updated["points"][0]["name"] == "四姑娘山"
    assert len(updated["stops"]) == 1 and updated["stops"][0]["stop_type"] == "charging"

    got = archive.get_routebook(book["id"])
    assert len(got["points"]) == 1 and len(got["stops"]) == 1
    with archive._session() as s:  # 旧点/停靠已整表替换（级联语义）
        rows = s.scalars(select(RoutePoint).where(RoutePoint.routebook_id == book["id"])).all()
        assert len(rows) == 1 and rows[0].name == "四姑娘山"
        assert len(s.scalars(select(RouteStop).where(RouteStop.routebook_id == book["id"])).all()) == 1


def test_delete_routebook_cascades(archive: Archive):
    book = archive.create_routebook("x", points=[A_POINT, B_POINT], stops=[A_STOP])
    archive.delete_routebook(book["id"])
    assert archive.get_routebook(book["id"]) is None
    assert archive.list_routebooks() == []
    with archive._session() as s:
        assert s.scalars(select(RoutePoint).where(RoutePoint.routebook_id == book["id"])).all() == []
        assert s.scalars(select(RouteStop).where(RouteStop.routebook_id == book["id"])).all() == []


def test_delete_routebook_missing(archive: Archive):
    with pytest.raises(ValueError, match="路书不存在"):
        archive.delete_routebook(999999)