"""数据根目录与运行时配置。

所有用户数据都必须位于数据根目录内，代码中只存相对路径（ADR-0002）。
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_TIMEZONE = "Asia/Shanghai"
DB_FILENAME = "travel.db"


def resolve_data_root(override: str | Path | None = None) -> Path:
    raw = override if override is not None else os.environ.get("TRAVEL_DATA_ROOT", "travel_data")
    return Path(raw).expanduser().resolve()


def ensure_layout(root: Path) -> None:
    for name in ("media", "thumbs", "exports", "tmp"):
        (root / name).mkdir(parents=True, exist_ok=True)
