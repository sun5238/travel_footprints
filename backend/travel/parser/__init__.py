"""M2 文本导入解析器（统一 `@` 标签 + 只切不认，见 docs/import-draft.md §1/§2）。

`parse_text(text, tz)` 返回「骨架草案」dict（标题/备注/trip 区间/城市候选/事件候选/灰行），
供校正页人工确认后入库；本包不落库、不识别开放词表、不做 LLM（ADR-0004）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..config import DEFAULT_TIMEZONE

from .skeleton import DraftBuilder

__all__ = ["parse_text"]


def parse_text(
    text: str,
    tz: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """便签文本 → 骨架草案 dict。`now` 可注入保证日期推算确定性（测试用）。"""
    builder = DraftBuilder(tz, now)
    for line_no, raw in enumerate(text.splitlines(), start=1):
        builder.feed(line_no, raw)
    return builder.build()