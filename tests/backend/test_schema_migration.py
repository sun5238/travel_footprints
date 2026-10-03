"""schema v1 -> 当前(v3) 迁移测试（铁律 3）：加列、轨迹并入删表、有数据拒迁、全新库直建当前版本。

以 raw SQL 模拟 v1 数据根，再用 Archive 打开触发迁移，验证列/数据/版本。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from travel.store import Archive

_V1_TABLES = """
CREATE TABLE visit (
    id INTEGER PRIMARY KEY,
    place_id INTEGER NOT NULL,
    trip_id INTEGER,
    at_local TEXT,
    at_tz TEXT DEFAULT 'Asia/Shanghai' NOT NULL,
    at_epoch REAL,
    rating INTEGER,
    review TEXT DEFAULT '' NOT NULL,
    place_name_snapshot TEXT DEFAULT '' NOT NULL,
    tags TEXT DEFAULT '[]' NOT NULL,
    created_epoch REAL
);
CREATE TABLE transport_leg (
    id INTEGER PRIMARY KEY,
    trip_id INTEGER NOT NULL,
    from_text TEXT DEFAULT '' NOT NULL,
    to_text TEXT DEFAULT '' NOT NULL,
    mode TEXT DEFAULT '其他' NOT NULL,
    depart_local TEXT,
    depart_tz TEXT DEFAULT 'Asia/Shanghai' NOT NULL,
    depart_epoch REAL,
    arrive_local TEXT,
    arrive_tz TEXT DEFAULT 'Asia/Shanghai' NOT NULL,
    arrive_epoch REAL,
    note TEXT DEFAULT '' NOT NULL,
    sort_order INTEGER DEFAULT 0 NOT NULL
);
CREATE TABLE trail (
    id INTEGER PRIMARY KEY,
    trip_id INTEGER,
    name TEXT DEFAULT '' NOT NULL,
    start_local TEXT, start_tz TEXT, start_epoch REAL,
    end_local TEXT, end_tz TEXT, end_epoch REAL,
    summit_local TEXT, summit_tz TEXT, summit_epoch REAL,
    gpx_path TEXT, drawn_geojson TEXT,
    distance_m REAL, elevation_gain_m REAL,
    note TEXT DEFAULT '' NOT NULL
);
"""


def _make_v1_db(data_root: Path, trail_rows: int = 0) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_root / "travel.db")
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.executescript(_V1_TABLES)
    conn.execute(
        "INSERT INTO visit (id, place_id, trip_id, at_local, place_name_snapshot) "
        "VALUES (1, 1, NULL, '2024-10-01T08:00:00', '宽窄巷子')"
    )
    conn.execute(
        "INSERT INTO transport_leg (id, trip_id, from_text, to_text, mode) "
        "VALUES (1, 1, '重庆北', '成都东', '高铁')"
    )
    for i in range(trail_rows):
        conn.execute(
            "INSERT INTO trail (id, trip_id, name) VALUES (?, ?, ?)", (i + 1, 1, f"轨迹{i}")
        )
    conn.commit()
    conn.close()


def _columns(db: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db)
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    conn.close()
    return cols


def _version(db: Path) -> int:
    conn = sqlite3.connect(db)
    (version,) = conn.execute("SELECT version FROM schema_version").fetchone()
    conn.close()
    return version


def _tables(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return names


def test_v1_opens_and_migrates_to_current_with_data_intact(data_root):
    _make_v1_db(data_root)
    archive = Archive(data_root)

    assert _version(data_root / "travel.db") == 3
    visit_cols = _columns(data_root / "travel.db", "visit")
    assert {"label", "companions", "pos_kind", "gpx_path", "drawn_geojson", "difficulty"} <= visit_cols
    assert _columns(data_root / "travel.db", "transport_leg") >= {"price"}

    visits = archive.list_visits()
    assert len(visits) == 1
    v = visits[0]
    assert v["at"]["local"] == "2024-10-01T08:00:00"
    assert v["place_name_snapshot"] == "宽窄巷子"
    assert v["label"] is None
    assert v["companions"] == []  # 旧行缺省 -> '[]'
    assert v["pos_kind"] == "none"
    assert v["gpx_path"] is None

    # trail 表已并入删除
    conn = sqlite3.connect(data_root / "travel.db")
    trail_exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='trail'"
    ).fetchone()[0]
    conn.close()
    assert trail_exists == 0

    # v3：路书表已建立
    assert {"routebook", "route_point", "route_stop"} <= _tables(data_root / "travel.db")

    archive.update_visit(visits[0]["id"], {"label": "城市漫游", "rating": 4})
    updated = archive.list_visits()[0]
    assert updated["label"] == "城市漫游" and updated["rating"] == 4
    archive.close()


def test_v1_with_trail_rows_refuses_migration(data_root):
    _make_v1_db(data_root, trail_rows=2)
    with pytest.raises(RuntimeError, match="trail"):
        Archive(data_root)
    # 拒绝迁移：版本仍为 1，列未改动（事务回滚，数据安全）
    assert _version(data_root / "travel.db") == 1
    assert "label" not in _columns(data_root / "travel.db", "visit")


def test_fresh_root_is_current_and_has_no_trail(data_root):
    archive = Archive(data_root)
    archive.close()
    db = data_root / "travel.db"
    assert _version(db) == 3
    assert "label" in _columns(db, "visit")
    assert "price" in _columns(db, "transport_leg")
    assert {"routebook", "route_point", "route_stop"} <= _tables(db)
    assert "trail" not in _tables(db)


def test_reopen_is_idempotent(data_root):
    _make_v1_db(data_root)
    Archive(data_root).close()
    second = Archive(data_root)  # 再开不应重复迁移/报错
    assert _version(data_root / "travel.db") == 3
    assert len(second.list_visits()) == 1  # 旧行未被破坏
    second.close()