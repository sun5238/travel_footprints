"""schema v2 -> v3 迁移测试（铁律 3）：新增 routebook/route_point/route_stop 表。

以 raw SQL 模拟 v2 数据根（含旧行程/到访数据），再用 Archive 打开触发迁移，
验证表已建、版本升至 3、旧数据完好。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from travel.store import Archive

_V2_MIN_TABLES = """
CREATE TABLE trip (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    note TEXT DEFAULT '' NOT NULL,
    start_local TEXT, start_tz TEXT DEFAULT 'Asia/Shanghai' NOT NULL, start_epoch REAL,
    end_local TEXT, end_tz TEXT DEFAULT 'Asia/Shanghai' NOT NULL, end_epoch REAL,
    tags TEXT DEFAULT '[]' NOT NULL,
    created_epoch REAL, updated_epoch REAL
);
CREATE TABLE visit (
    id INTEGER PRIMARY KEY,
    place_id INTEGER NOT NULL,
    trip_id INTEGER,
    at_local TEXT, at_tz TEXT DEFAULT 'Asia/Shanghai' NOT NULL, at_epoch REAL,
    rating INTEGER, review TEXT DEFAULT '' NOT NULL,
    place_name_snapshot TEXT DEFAULT '' NOT NULL,
    tags TEXT DEFAULT '[]' NOT NULL,
    label TEXT, companions TEXT DEFAULT '[]' NOT NULL,
    pos_kind TEXT DEFAULT 'none' NOT NULL, gpx_path TEXT, drawn_geojson TEXT, difficulty TEXT,
    created_epoch REAL
);
"""


def _make_v2_db(data_root: Path) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_root / "travel.db")
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version (version) VALUES (2)")
    conn.executescript(_V2_MIN_TABLES)
    conn.execute("INSERT INTO trip (id, name) VALUES (1, '老行程')")
    conn.execute(
        "INSERT INTO visit (id, place_id, at_local, place_name_snapshot, label) "
        "VALUES (1, 1, '2025-03-01T09:00:00', '老店', 'city')"
    )
    conn.commit()
    conn.close()


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


def test_fresh_root_is_v3_with_routebook_tables(data_root):
    archive = Archive(data_root)
    archive.close()
    db = data_root / "travel.db"
    assert _version(db) == 3
    assert {"routebook", "route_point", "route_stop"} <= _tables(db)


def test_v2_opens_and_migrates_to_v3_with_data_intact(data_root):
    _make_v2_db(data_root)
    archive = Archive(data_root)

    assert _version(data_root / "travel.db") == 3
    assert {"routebook", "route_point", "route_stop"} <= _tables(data_root / "travel.db")

    trips = archive.list_trips()
    assert len(trips) == 1 and trips[0]["name"] == "老行程"
    visits = archive.list_visits()
    assert len(visits) == 1
    assert visits[0]["label"] == "city"
    assert visits[0]["place_name_snapshot"] == "老店"
    archive.close()


def test_reopen_is_idempotent(data_root):
    _make_v2_db(data_root)
    Archive(data_root).close()
    second = Archive(data_root)  # 再开不应重复迁移/报错
    assert _version(data_root / "travel.db") == 3
    assert len(second.list_trips()) == 1
    second.close()