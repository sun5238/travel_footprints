"""时间规则：实体时间以「本地挂钟时间 + IANA 时区」存储，派生 Unix 时间戳用于排序（ADR-0006）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import DEFAULT_TIMEZONE


def parse_local(local: str | datetime, tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区: {tz_name}") from exc
    dt = datetime.fromisoformat(local) if isinstance(local, str) else local
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
    return dt


def to_epoch(local: str | datetime | None, tz_name: str = DEFAULT_TIMEZONE) -> float | None:
    if local is None or local == "":
        return None
    return parse_local(local, tz_name).timestamp()


def to_local_iso(local: str | datetime | None, tz_name: str = DEFAULT_TIMEZONE) -> str | None:
    if local is None or local == "":
        return None
    return parse_local(local, tz_name).isoformat(timespec="seconds")
