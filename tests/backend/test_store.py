"""仓储层行为测试：CRUD、点亮规则、名称快照、删除语义。"""

from __future__ import annotations

from travel.store import Archive


def test_schema_initialized_and_idempotent(data_root):
    first = Archive(data_root)
    first.close()
    second = Archive(data_root)
    second.close()
    assert (data_root / "travel.db").exists()


def test_trip_crud_roundtrip(archive: Archive):
    created = archive.create_trip(
        "国庆成都行", start_local="2025-10-01T08:00:00", end_local="2025-10-07T20:00:00"
    )
    assert created["start"]["epoch"] is not None
    assert archive.get_trip(created["id"])["name"] == "国庆成都行"
    titles = [t["name"] for t in archive.list_trips()]
    assert "国庆成都行" in titles

    updated = archive.update_trip(created["id"], {"name": "国庆成都七日"})
    assert updated["name"] == "国庆成都七日"

    archive.delete_trip(created["id"])
    assert archive.get_trip(created["id"]) is None


def test_lit_cities_only_with_visits(archive: Archive):
    chengdu = archive.create_city("成都", lat=30.57, lng=104.07)
    archive.create_city("重庆")
    kuanzhai = archive.create_place("宽窄巷子", kind="scene", city_id=chengdu["id"], lat=30.66, lng=104.06)
    archive.create_visit(kuanzhai["id"], at_local="2025-10-02T20:00:00")

    lit = archive.list_cities(lit_only=True)
    names = {c["name"]: c for c in lit}
    assert set(names) == {"成都"}
    assert names["成都"]["visit_count"] == 1
    assert names["成都"]["place_count"] == 1

    archive.create_visit(kuanzhai["id"], at_local="2025-10-03T09:00:00")
    lit_after = {c["name"]: c for c in archive.list_cities(lit_only=True)}
    assert lit_after["成都"]["visit_count"] == 2
    assert "重庆" not in lit_after
    assert {c["name"] for c in archive.list_cities()} == {"成都", "重庆"}


def test_visit_keeps_name_snapshot_across_rename(archive: Archive):
    place = archive.create_place("李氏面馆", kind="shop")
    visit = archive.create_visit(place["id"], rating=5, review="好吃，面劲道")
    assert visit["place_name_snapshot"] == "李氏面馆"

    archive.update_place(place["id"], {"name": "李姐面馆"})
    visits = archive.list_visits(place_id=place["id"])
    assert visits[0]["place_name_snapshot"] == "李氏面馆"


def test_delete_visit_detaches_media_to_pending(archive: Archive, tmp_path, photo_bytes):
    place = archive.create_place("锦里", kind="scene")
    visit = archive.create_visit(place["id"])
    src = tmp_path / "a.png"
    src.write_bytes(photo_bytes)
    media = archive.ingest_media_path(src, "a.png", visit_id=visit["id"])
    assert media["status"] == "attached"

    archive.delete_visit(visit["id"])
    rows = archive.list_media(status="pending")
    assert len(rows) == 1 and rows[0]["id"] == media["id"]
    assert rows[0]["visit_id"] is None


def test_delete_place_detaches_media_and_visits(archive: Archive, tmp_path, photo_bytes):
    place = archive.create_place("太古里", kind="scene")
    visit = archive.create_visit(place["id"])
    src = tmp_path / "b.png"
    src.write_bytes(photo_bytes)
    archive.ingest_media_path(src, "b.png", visit_id=visit["id"])

    archive.delete_place(place["id"])
    assert archive.list_visits(place_id=place["id"]) == []
    pending = archive.list_media(status="pending")
    assert len(pending) == 1 and pending[0]["visit_id"] is None


def test_create_city_autofills_center_coords(archive: Archive):
    city = archive.create_city("成都")
    assert city["lat"] is not None and city["lng"] is not None
    assert abs(city["lat"] - 30.5723) < 0.01
    assert abs(city["lng"] - 104.0668) < 0.01


def test_unknown_city_keeps_null_coords(archive: Archive):
    city = archive.create_city("某个小镇")
    assert city["lat"] is None and city["lng"] is None


def test_explicit_coords_win_over_static_table(archive: Archive):
    city = archive.create_city("成都", lat=1.0, lng=2.0)
    assert city["lat"] == 1.0 and city["lng"] == 2.0


def test_dashboard_label_stats_groups_by_label(archive: Archive):
    place = archive.create_place("磁器口古镇", kind="scene")
    for at, label in [
        ("2024-10-06T10:00:00", "古镇"),
        ("2024-10-07T10:00:00", "古镇"),
        ("2024-10-08T10:00:00", "爬山"),
        ("2024-10-09T10:00:00", None),
    ]:
        archive.create_visit(place["id"], at_local=at, label=label)
    stats = archive.dashboard()["stats"]
    assert stats["label_stats"] == [{"label": "古镇", "count": 2}, {"label": "爬山", "count": 1}]
    # M2：轨迹并入 visit，看板不再有轨迹数/总里程
    assert "distance_km" not in stats and "trails" not in stats
