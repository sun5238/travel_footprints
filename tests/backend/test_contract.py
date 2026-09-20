"""HTTP 契约测试（A 层）：断言端点返回 JSON 的结构、字段类型、嵌套与错误路径。

权威结构基准：travel/store.py 的序列化器（_city_dict/_place_dict/_visit_dict/
_media_dict/_leg_dict/_trip_dict 与 dashboard）。本测试把「实际 HTTP 响应」与这些
结构对齐，防止后端改坏对外契约；同时覆盖空库零值分支、二进制端点语义与错误路径。
"""

from __future__ import annotations

import io
import zipfile

# ---- 各端点响应的权威键集合（与 store 序列化器一一对应） ----

CITY_KEYS = {"id", "name", "lat", "lng", "note", "lit", "visit_count", "place_count"}
PLACE_KEYS = {"id", "city_id", "kind", "name", "lat", "lng", "note", "lit", "visit_count"}
VISIT_KEYS = {
    "id", "place_id", "trip_id", "at", "rating", "review",
    "place_name_snapshot", "tags", "created_epoch",
}
MEDIA_KEYS = {
    "id", "kind", "status", "visit_id", "trip_id", "city_id",
    "taken_at", "gps", "size_bytes", "file", "thumb",
}
LEG_KEYS = {"id", "trip_id", "from", "to", "mode", "depart", "arrive", "note", "sort_order"}
TRIP_KEYS = {"id", "name", "note", "start", "end", "tags", "created_epoch", "updated_epoch"}
DASH_STATS_KEYS = {"cities_lit", "cities", "places", "visits", "media", "media_pending", "trails", "distance_km"}

# 种子数据规模（seed.py 校验后的基准值）
EXPECTED = {
    "cities": 4,
    "lit_cities": 3,
    "places": 14,
    "visits": 17,
    "media": 64,
    "media_pending": 2,
}


def _assert_subkeys(item: dict, keys: set[str]) -> None:
    """断言响应的键集合与权威序列化器完全一致（不多不少）。"""
    assert set(item) == keys, f"键集与权威不一致: {set(item) ^ keys}"


def _assert_num(n, allow_none=False):
    assert n is None or isinstance(n, (int, float)), f"非数字: {n!r}"


def _assert_at_shape(at: dict) -> None:
    _assert_subkeys(at, {"local", "tz", "epoch"})
    assert isinstance(at["local"], (str, type(None)))
    assert isinstance(at["tz"], str)
    _assert_num(at["epoch"])


# ---------- 看板 ----------

def test_dashboard_contract(seeded_client):
    dash = seeded_client.get("/api/dashboard").json()
    _assert_subkeys(dash, {"stats", "lit_cities", "recent_trips"})

    _assert_subkeys(dash["stats"], DASH_STATS_KEYS)
    assert isinstance(dash["stats"]["cities_lit"], int)
    assert isinstance(dash["stats"]["cities"], int)
    assert isinstance(dash["stats"]["places"], int)
    assert isinstance(dash["stats"]["visits"], int)
    assert isinstance(dash["stats"]["media"], int)
    assert isinstance(dash["stats"]["media_pending"], int)
    assert isinstance(dash["stats"]["trails"], int)
    assert isinstance(dash["stats"]["distance_km"], float)

    assert dash["stats"]["cities_lit"] == EXPECTED["lit_cities"]
    assert dash["stats"]["media_pending"] == EXPECTED["media_pending"]


def test_dashboard_lit_cities_contract(seeded_client):
    dash = seeded_client.get("/api/dashboard").json()
    lit = dash["lit_cities"]
    assert len(lit) == EXPECTED["lit_cities"]
    for c in lit:
        _assert_subkeys(c, CITY_KEYS)
        assert isinstance(c["name"], str)
        _assert_num(c["lat"]); _assert_num(c["lng"])
        assert isinstance(c["visit_count"], int) and c["visit_count"] >= 1
        assert isinstance(c["place_count"], int) and c["place_count"] >= 1
        assert c["lit"] is True
    names = {c["name"] for c in lit}
    assert {"成都", "重庆", "广州"} <= names
    assert "贵阳" not in names  # 路过城市不点亮


# ---------- 城市 ----------

def test_cities_contract(seeded_client):
    cities = seeded_client.get("/api/cities").json()
    assert len(cities) == EXPECTED["cities"]
    for c in cities:
        _assert_subkeys(c, CITY_KEYS)
        assert isinstance(c["name"], str)
        assert isinstance(c["lit"], bool)
        assert isinstance(c["visit_count"], int)
        assert isinstance(c["place_count"], int)
    by_name = {c["name"]: c for c in cities}
    assert by_name["贵阳"]["lit"] is False and by_name["贵阳"]["visit_count"] == 0
    assert by_name["成都"]["lit"] is True

    lit = seeded_client.get("/api/cities?lit=1").json()
    assert len(lit) == EXPECTED["lit_cities"]


def test_city_404(seeded_client):
    resp = seeded_client.get("/api/cities/999999")
    assert resp.status_code == 404
    assert resp.json()["detail"]


def test_city_duplicate_400(seeded_client):
    resp = seeded_client.post("/api/cities", json={"name": "成都"})
    assert resp.status_code == 400
    assert "已存在" in resp.json()["detail"]


# ---------- 地点 ----------

def test_places_contract(seeded_client):
    places = seeded_client.get("/api/places?lit=1").json()
    assert len(places) == EXPECTED["places"]
    kinds = set()
    has_null_coords = False
    for p in places:
        _assert_subkeys(p, PLACE_KEYS)
        assert p["kind"] in ("scene", "shop", "landmark")
        _assert_num(p["lat"]); _assert_num(p["lng"])
        if p["lat"] is None or p["lng"] is None:
            has_null_coords = True
        kinds.add(p["kind"])
        assert isinstance(p["visit_count"], int)
        assert p["lit"] is True
    assert kinds == {"scene", "shop", "landmark"}
    assert has_null_coords  # 有"无坐标"态（餐馆/留空）


def test_place_invalid_kind_422(seeded_client):
    """kind 由 Pydantic Literal 校验，非法值在请求校验层即返回 422。"""
    resp = seeded_client.post("/api/places", json={"name": "某地", "kind": "void"})
    assert resp.status_code == 422
    assert "kind" in resp.json()["detail"][0]["loc"]


# ---------- 到访 ----------

def test_visits_contract(seeded_client):
    visits = seeded_client.get("/api/visits").json()
    assert len(visits) == EXPECTED["visits"]
    years = set()
    has_null_rating = False
    for v in visits:
        _assert_subkeys(v, VISIT_KEYS)
        assert isinstance(v["place_id"], int)
        assert isinstance(v["trip_id"], (int, type(None)))
        _assert_at_shape(v["at"])
        if v["rating"] is None:
            has_null_rating = True
        else:
            assert isinstance(v["rating"], int) and 1 <= v["rating"] <= 5
        assert isinstance(v["review"], str)
        assert isinstance(v["place_name_snapshot"], str) and v["place_name_snapshot"]
        assert isinstance(v["tags"], list)
        if v["at"]["local"] and len(v["at"]["local"]) >= 4:
            years.add(v["at"]["local"][:4])
    assert has_null_rating  # 无评分分支
    assert {"2024", "2025"} <= years  # 跨年，供前端年份过滤


def test_visits_by_trip(seeded_client):
    trip_id = seeded_client.get("/api/trips").json()[0]["id"]
    filtered = seeded_client.get(f"/api/visits?trip_id={trip_id}").json()
    assert filtered
    assert all(v["trip_id"] == trip_id for v in filtered)


def test_visit_invalid_rating_422(seeded_client):
    """rating 由 Pydantic ge/le 校验，越界值返回 422。"""
    place_id = seeded_client.get("/api/places").json()[0]["id"]
    resp = seeded_client.post(f"/api/places/{place_id}/visits", json={"rating": 9})
    assert resp.status_code == 422
    assert "rating" in resp.json()["detail"][0]["loc"]


# ---------- 媒体 ----------

def test_media_contract(seeded_client):
    media = seeded_client.get("/api/media").json()
    assert len(media) == EXPECTED["media"]
    kinds = set()
    statuses = set()
    has_gps = False
    for m in media:
        _assert_subkeys(m, MEDIA_KEYS)
        kinds.add(m["kind"])
        statuses.add(m["status"])
        assert isinstance(m["size_bytes"], int)
        assert m["file"].startswith("/api/media/")
        assert m["thumb"].startswith("/api/media/")
        _assert_at_shape(m["taken_at"])
        gps = m["gps"]
        _assert_subkeys(gps, {"lat", "lng", "accuracy"})
        if gps["lat"] is not None and gps["lng"] is not None:
            has_gps = True
    assert kinds == {"photo", "video"}
    assert statuses == {"attached", "pending"}
    assert has_gps


def test_media_pending_status(seeded_client):
    pending = seeded_client.get("/api/media?status=pending").json()
    assert len(pending) == EXPECTED["media_pending"]
    assert all(m["status"] == "pending" and m["visit_id"] is None for m in pending)


def test_media_binary_semantics(seeded_client):
    """文件端点全部可读非空；缩略图：真图 200+jpeg，占位/视频 404（容错路径）。"""
    media = seeded_client.get("/api/media").json()
    thumb_ok = thumb_404 = 0
    for m in media:
        f = seeded_client.get(m["file"])
        assert f.status_code == 200 and len(f.content) > 0
        t = seeded_client.get(m["thumb"])
        if t.status_code == 200:
            assert t.headers["content-type"] == "image/jpeg"
            thumb_ok += 1
        elif t.status_code == 404:
            thumb_404 += 1
        else:
            raise AssertionError(f"缩略图异常状态码: {t.status_code}")
    assert thumb_ok >= 1 and thumb_404 >= 1


# ---------- 行程与交通段 ----------

def test_trips_contract(seeded_client):
    trips = seeded_client.get("/api/trips").json()
    assert len(trips) == 2
    for t in trips:
        _assert_subkeys(t, TRIP_KEYS)
        assert isinstance(t["name"], str)
        _assert_at_shape(t["start"])
        _assert_at_shape(t["end"])
        assert isinstance(t["tags"], list)
    by_name = {t["name"]: t for t in trips}
    assert set(by_name) == {"国庆成都行", "周末广州行"}


def test_legs_contract(seeded_client):
    trips = seeded_client.get("/api/trips").json()
    by_name = {t["name"]: t for t in trips}
    trip1_legs = seeded_client.get(f"/api/trips/{by_name['国庆成都行']['id']}/legs").json()
    assert len(trip1_legs) == 3
    modes = {l["mode"] for l in trip1_legs}
    assert {"高铁", "飞机", "自驾"} <= modes
    for leg in trip1_legs:
        _assert_subkeys(leg, LEG_KEYS)
        assert isinstance(leg["from"], str) and isinstance(leg["to"], str)
        assert isinstance(leg["sort_order"], int)
    assert [l["sort_order"] for l in trip1_legs] == sorted(l["sort_order"] for l in trip1_legs)

    trip2_legs = seeded_client.get(f"/api/trips/{by_name['周末广州行']['id']}/legs").json()
    assert {l["mode"] for l in trip2_legs} == {"大巴", "飞机"}


# ---------- 备份与恢复（二进制语义） ----------

def test_backup_binary_semantics(seeded_client):
    resp = seeded_client.get("/api/backup")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "travel-footprints-backup" in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
    assert any(n.endswith("travel.db") for n in names)
    assert any(n.startswith("media/") for n in names)


# ---------- 空库零值分支 ----------

def test_empty_db_zero_shape(client):
    dash = client.get("/api/dashboard").json()
    assert dash["stats"]["cities_lit"] == 0
    assert dash["stats"]["cities"] == 0
    assert dash["stats"]["places"] == 0
    assert dash["stats"]["visits"] == 0
    assert dash["stats"]["media"] == 0
    assert dash["stats"]["media_pending"] == 0
    assert dash["stats"]["trails"] == 0
    assert dash["stats"]["distance_km"] == 0.0
    assert dash["lit_cities"] == []
    assert dash["recent_trips"] == []
    assert client.get("/api/media").json() == []
    assert client.get("/api/visits").json() == []
    assert client.get("/api/places?lit=1").json() == []