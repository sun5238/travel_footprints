"""时间语法（导入草案 §2.3 收窄版）：只识别至少明确月日的日期 / 区间 / 时刻。

输出日期候选（`DatePart`）与跨行继承状态（`DateResolver`）。纯函数、无 I/O：
日期最终按「本地挂钟时间」输出为朴素本地 ISO 字符串，IANA 时区由上层携带
（对齐 timeutil.py 的「本地时间 + 时区」存储口径，ADR-0006）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..config import DEFAULT_TIMEZONE

# ---------------------------------------------------------------- 词法模式

_Y = r"\d{4}"
_D = r"(?:0?[1-9]|[12]\d|3[01])"

_YYMMDD = rf"{_Y}[-./]{_D}[-./]{_D}"          # 2026-10-01 / 2026.10.1 / 2026/10/1
_MMDD_CN = r"\d{1,2}月\d{1,2}[号日]"          # 10月1号 / 10月1日
_MMDD_SEP = r"\d{1,2}[-./]\d{1,2}"            # 10.1 / 10-1
_DAY_CN = r"\d{1,2}号"                        # 2号（只给日，年/月自上下文）
DATE_PIECE = rf"(?:{_YYMMDD}|{_MMDD_CN}|{_MMDD_SEP}|{_DAY_CN})"

_RANGE_SEP = r"(?:到|至|~|～)"
TIME_HM = r"(?:[01]\d|2[0-3]):[0-5]\d"        # HH:MM

_DATE_RE = re.compile(DATE_PIECE)
_RANGE_BETWEEN = re.compile(rf"\s*(?:{_RANGE_SEP})\s*$")
_TIME_RE = re.compile(rf"(?<!\d){TIME_HM}(?!\d)")

_CHINESE_PREFIXES = {"一二三四五六七八九十"}
# 中文数字日期写法（十月一号）超出收窄范围，不做——见草案 §2.3。


@dataclass(frozen=True)
class DatePart:
    """一个日期片段，允许缺项：(year|None, month|None, day|None)。"""

    year: int | None = None
    month: int | None = None
    day: int | None = None

    @property
    def has_month(self) -> bool:
        return self.month is not None or self.year is not None


@dataclass(frozen=True)
class DateRange:
    """区间 START 到|至|~|～ END，END 可缺年/月（沿用 START）。"""

    start: DatePart
    end: DatePart
    text: str


def parse_date_piece(text: str) -> DatePart | None:
    """把一个日期片段文本解析为 DatePart；不是合法日期形态返回 None。"""
    text = text.strip()
    m = re.fullmatch(rf"({_Y})[-./](\d{{1,2}})[-./](\d{{1,2}})", text)
    if m:
        return DatePart(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"(\d{1,2})月(\d{1,2})[号日]", text)
    if m:
        return DatePart(None, int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"(\d{1,2})[-./](\d{1,2})", text)
    if m:
        return DatePart(None, int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"(\d{1,2})号", text)
    if m:
        return DatePart(None, None, int(m.group(1)))
    return None


def scan_dates(line: str) -> tuple[list[tuple[int, int, DateRange]], list[tuple[int, int, DatePart]]]:
    """扫描一行中的日期片段与区间。

    返回 (ranges, singles)：ranges 为相邻日期片段被区间分隔(`到|至|~|～`)连成的区间，
    singles 为其余单个日期片段；每项带 (start, end) 字节区间，供上层剥除原文。
    """
    matches = [
        (m.start(), m.end(), part)
        for m in _DATE_RE.finditer(line)
        if (part := parse_date_piece(m.group(0))) is not None
    ]
    ranges: list[tuple[int, int, DateRange]] = []
    consumed: set[int] = set()
    for idx in range(len(matches) - 1):
        a_start, a_end, a_part = matches[idx]
        b_start, b_end, b_part = matches[idx + 1]
        between = line[a_end:b_start]
        if _RANGE_BETWEEN.fullmatch(between):
            span = line[a_start:b_end]
            ranges.append((a_start, b_end, DateRange(a_part, b_part, span)))
            consumed.update((idx, idx + 1))
    singles = [(s, e, p) for i, (s, e, p) in enumerate(matches) if i not in consumed]
    return ranges, singles


def scan_times(line: str) -> list[tuple[int, int, str]]:
    """扫描一行中的 HH:MM 时刻，返回 (start, end, 'HH:MM')。"""
    return [(m.start(), m.end(), m.group(0)) for m in _TIME_RE.finditer(line)]


# ---------------------------------------------------------------- 日期状态继承

class DateResolver:
    """跨行的日期状态机（草案 §2.3 日期状态继承）：

    - 显式完整/月日日期更新状态；`X号` 只给「日」，年/月自上下文补齐；
    - `now` 可注入（测试确定性），缺年时按当前时区「当年」兜底。
    无法补齐时为 (date(1,1,1), False)，调用方标灰交校正页，不静默猜。
    """

    def __init__(self, tz: str = DEFAULT_TIMEZONE, now: datetime | None = None) -> None:
        self.tz = tz
        self.now = now if now is not None else datetime.now(ZoneInfo(tz))
        self.year: int | None = None
        self.month: int | None = None
        self.day: int | None = None

    def set_explicit(self, part: DatePart) -> None:
        if part.year:
            self.year = part.year
        if part.month:
            self.month = part.month
        if part.day:
            self.day = part.day
        if self.year is None:
            self.year = self.now.year  # 缺年默认当年（跨年按时区处理）

    def set_from_date(self, d: date) -> None:
        self.year, self.month, self.day = d.year, d.month, d.day

    def current_date(self) -> date | None:
        if self.year is None or self.month is None or self.day is None:
            return None
        try:
            return date(self.year, self.month, self.day)
        except ValueError:
            return None

    def resolve(self, part: DatePart) -> tuple[date, bool]:
        """解析一个片段为完整日期；缺项按状态/当年补齐。"""
        year = part.year or self.year or self.now.year
        month = part.month or self.month
        day = part.day
        if year is None or month is None or day is None:
            return date(1, 1, 1), False
        try:
            return date(year, month, day), True
        except ValueError:
            return date(1, 1, 1), False


def local_iso(d: date, hm: str | None = None) -> str:
    """date(+可选 HH:MM) → 朴素本地 ISO 字符串（无时区后缀）。"""
    if hm:
        h, _, m = hm.partition(":")
        return f"{d.isoformat()}T{int(h):02d}:{int(m):02d}:00"
    return f"{d.isoformat()}T00:00:00"