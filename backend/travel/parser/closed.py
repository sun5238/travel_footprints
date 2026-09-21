"""封闭剥离（导入草案 §1/§2.4）：星级、交通方式、关系词提示符。

只剥「候选」，不代判定：剥出的值由上层预填校正页，判定权在人工；
剥离失败/缺失则留在原文，绝不静默断言。
"""

from __future__ import annotations

import re

CHINESE_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}

# 星级形态：`5星` / `五星` / `★5`。一级只剥一个、且须紧随时刻 token 之后（见 strip_rating）。
_STAR_RE = re.compile(r"(?:(\d)|([一二三四五]))星|★(\d)")

# 交通方式封闭词表（草案 §1「约 10 词」）。长词优先，避免「大巴」被「巴」类误配。
MODES: tuple[str, ...] = (
    "高铁", "动车", "火车", "飞机", "自驾", "徒步", "骑行", "公交", "地铁", "大巴", "船", "打车", "其他",
)
_MODES = tuple(sorted(MODES, key=len, reverse=True))

# 关系词提示符：不用于类型判定，仅作校正页提示。
TRAIL_WORDS: tuple[str, ...] = ("登顶", "结束", "下山", "下撤", "开始", "起点", "终点")


def star_value(text: str) -> int | None:
    m = _STAR_RE.search(text)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    if m.group(2):
        return CHINESE_DIGITS[m.group(2)]
    return int(m.group(3))


_STAR_BOUNDARY = ",，。、;；!！?？)）]"


def _is_star_boundary(ch: str) -> bool:
    return ch.isspace() or ch in _STAR_BOUNDARY


def strip_rating(line: str, time_end: int) -> tuple[int | None, int, int]:
    """剥行内紧贴时刻 token 之后的第一个星级（草案 §2.4 裂缝 5）。

    - 仅剥时刻 token（time_end）之后「紧贴」（其间只允许空白）的第一个 `N星`/`★N`，
      一行只剥一个；
    - 星级须是独立 token（后随空白/标点/行尾），正文里的「5星大厨」类不剥；
    - 无时刻锚（time_end<=0）→ 不命中；
    - 返回 (rating, star_start, star_end)，未剥出时 (None, -1, -1)。
    """
    if time_end <= 0 or time_end >= len(line):
        return None, -1, -1
    m = _STAR_RE.search(line, time_end)
    if not m:
        return None, -1, -1
    if line[time_end:m.start()].strip():  # 星与时刻之间有非空白 → 非紧贴，不剥
        return None, -1, -1
    if m.end() < len(line) and not _is_star_boundary(line[m.end()]):
        return None, -1, -1  # 星级后紧跟汉字（如 5星大厨）→ 非独立星级，不剥
    return star_value(m.group(0)), m.start(), m.end()


def find_mode(text: str) -> str | None:
    """在文本中找第一个交通方式候选（长词优先）。"""
    for word in _MODES:
        if word in text:
            return word
    return None


def has_trail_hint(text: str) -> bool:
    """是否含疑似轨迹关系词（登顶/结束/…）。"""
    return any(w in text for w in TRAIL_WORDS)