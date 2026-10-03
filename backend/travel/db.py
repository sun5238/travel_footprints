"""SQLite 连接、schema 初始化与版本化（铁律 3：schema 版本化，不得静默改表）。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from . import models
from .config import DB_FILENAME

SCHEMA_VERSION = 3

# v1 -> v2（M2，见 import-draft.md §7）：
#   独立 trail 表并入 visit（visit 自增轨迹增强列）后删除；transport_leg 增 price。
#   trail 表如仍有数据则拒绝迁移（避免静默丢数据，铁律 3）。
_V1_TO_V2_SQL = (
    "ALTER TABLE visit ADD COLUMN label TEXT",
    "ALTER TABLE visit ADD COLUMN companions TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE visit ADD COLUMN pos_kind TEXT NOT NULL DEFAULT 'none'",
    "ALTER TABLE visit ADD COLUMN gpx_path TEXT",
    "ALTER TABLE visit ADD COLUMN drawn_geojson TEXT",
    "ALTER TABLE visit ADD COLUMN difficulty TEXT",
    "ALTER TABLE transport_leg ADD COLUMN price REAL",
)

# v2 -> v3（M4 路书，ADR-0008）：新增路书 + 途经点 + 线上停靠标注三张表（纯增量建表）。
_V2_TO_V3_SQL = (
    """
    CREATE TABLE IF NOT EXISTS routebook (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'driving',
        preset TEXT NOT NULL DEFAULT 'balanced',
        mileage_km REAL,
        mileage_manual BOOLEAN NOT NULL DEFAULT 0,
        geometry_source TEXT NOT NULL DEFAULT 'engine',
        geometry_json TEXT,
        created_epoch REAL,
        updated_epoch REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS route_point (
        id INTEGER PRIMARY KEY,
        routebook_id INTEGER NOT NULL REFERENCES routebook(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL DEFAULT '',
        lat REAL,
        lng REAL,
        pos_kind TEXT NOT NULL DEFAULT 'none',
        stop_type TEXT,
        stop_name TEXT NOT NULL DEFAULT '',
        stop_note TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS route_stop (
        id INTEGER PRIMARY KEY,
        routebook_id INTEGER NOT NULL REFERENCES routebook(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL DEFAULT 0,
        name TEXT NOT NULL DEFAULT '',
        lat REAL,
        lng REAL,
        pos_kind TEXT NOT NULL DEFAULT 'none',
        stop_type TEXT NOT NULL DEFAULT 'scene',
        stop_note TEXT NOT NULL DEFAULT ''
    )
    """,
)


def connect(root: Path) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_engine(f"sqlite:///{root / DB_FILENAME}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # pragma: no cover - sqlite 细节
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    init_schema(engine)
    return engine, factory


def init_schema(engine: Engine) -> None:
    models.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"))
        row = conn.execute(text("SELECT version FROM schema_version")).fetchone()
        if row is None:
            conn.execute(text("INSERT INTO schema_version (version) VALUES (:v)"), {"v": SCHEMA_VERSION})
        elif row[0] < SCHEMA_VERSION:
            _upgrade(conn, row[0])
        elif row[0] > SCHEMA_VERSION:
            raise RuntimeError(
                f"数据根目录 schema 版本为 {row[0]}，代码需要 {SCHEMA_VERSION}；请先升级代码再继续。"
            )


def _upgrade(conn, current: int) -> None:
    """版本化迁移链（铁律 3）：仅上移，禁止降级；迁移在事务内完成，逐级升到当前版本。"""
    while current < SCHEMA_VERSION:
        if current == 1:
            # 阻塞项先行：有 trail 数据则拒绝迁移（SQLite DDL 会提前提交，必须 guard-first）
            trail_count = conn.execute(text("SELECT COUNT(*) FROM trail")).scalar()
            if trail_count:
                raise RuntimeError(
                    f"trail 表有 {trail_count} 条数据，无法自动并入 visit（M2 已取消独立轨迹表）；"
                    "请先手动备份/迁移后再升级。"
                )
            for statement in _V1_TO_V2_SQL:
                conn.execute(text(statement))
            conn.execute(text("DROP TABLE IF EXISTS trail"))
            current = 2
        elif current == 2:
            # 纯增量建表：create_all 已兜底创建，IF NOT EXISTS 保证迁移幂等
            for statement in _V2_TO_V3_SQL:
                conn.execute(text(statement))
            current = 3
        else:  # pragma: no cover - 防御：未知旧版本
            raise RuntimeError(f"不支持的 schema 版本起点: {current}")
        conn.execute(text("UPDATE schema_version SET version = :v"), {"v": current})
