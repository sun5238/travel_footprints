"""SQLite 连接、schema 初始化与版本化（铁律 3：schema 版本化，不得静默改表）。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from . import models
from .config import DB_FILENAME

SCHEMA_VERSION = 1


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
        elif row[0] != SCHEMA_VERSION:
            raise RuntimeError(
                f"数据根目录 schema 版本为 {row[0]}，代码需要 {SCHEMA_VERSION}；请先升级数据再继续。"
            )
