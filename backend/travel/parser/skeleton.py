"""骨架草案组装（草案 §2.1/§2.3/§2.5）：切行 + @ 词法 + 时间语法 + 封闭剥离，
按「先展示后入库、绝不静默错认」输出草案 dict。纯函数、无 I/O。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import DEFAULT_TIMEZONE
from . import closed
from .lexer import AtToken, classify_line, lex_at, split_transport
from .time_rules import (
    DateResolver,
    DateRange,
    DatePart,
    local_iso,
    parse_date_piece,
    scan_dates,
    scan_times,
)

TRIP_RANGE_GRAY = "区间中途出现或与既有 trip 区间重复，交校正页裁决"
STAR_IN_NAME_GRAY = "地址与星级未以空白分隔（如 @陈麻婆豆腐4星），交校正页修正"
DEFER_GRAY = "日期/结构不确定，交校正页补全"

# 名称吞星检测：token 以 N星 / 五X星 / ★N 结尾才判定失败（避免「五星饭店」误伤）
_STAR_SUFFIX = re.compile(r"(?:\d|[一二三四五])星$|★\d$")
_RELATION_SPANS = re.compile(r"->|~|～")


class DraftBuilder:
    """逐行喂入文本，累积标题/备注/区间/城市候选/事件/灰行，最终 build() 出草案。"""

    def __init__(self, tz: str = DEFAULT_TIMEZONE, now: datetime | None = None) -> None:
        self.tz = tz
        self.resolver = DateResolver(tz, now)
        self.title: str | None = None
        self.note_parts: list[str] = []
        self.trip_range: dict[str, str] | None = None
        self.cities: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.gray: list[dict[str, Any]] = []
        self._open_event: int | None = None
        self._seen_event = False
        self._seen_trip_range = False

    # ------------------------------------------------------------ 逐行喂入

    def feed(self, line_no: int, raw: str) -> None:
        kind = classify_line(raw)
        if kind == "blank":
            return
        if kind == "title":
            if self.title is None:
                self.title = raw.strip().lstrip("#").strip()
            return
        if kind == "continuation":
            self._merge_continuation(raw)
            return
        self._process_entity(line_no, raw)

    def build(self) -> dict[str, Any]:
        return {
            "tz": self.tz,
            "title": self.title,
            "note": " ".join(self.note_parts) if self.note_parts else None,
            "trip_range": self.trip_range,
            "cities": self.cities,
            "events": self.events,
            "gray": self.gray,
        }

    # ------------------------------------------------------------ 续行归并

    def _merge_continuation(self, raw: str) -> None:
        text = raw.strip()
        if not text:
            return
        if self._open_event is not None:
            event = self.events[self._open_event]
            event["review"] = (event["review"] + " " + text).strip()
        else:
            self.note_parts.append(text)

    # ------------------------------------------------------------ 实体行主流程

    def _process_entity(self, line_no: int, raw: str) -> None:
        tokens = lex_at(raw)
        ranges, singles = scan_dates(raw)
        times = scan_times(raw)

        name_tokens: list[AtToken] = []
        for t in tokens:
            if _is_name_token(t):
                name_tokens.append(t)

        # 名称吞星 → 解析失败，整行标灰（草案 §2.2 不对称规则，无宽容路径）
        if any(_STAR_SUFFIX.search(t.text) for t in name_tokens):
            self._add_gray(line_no, raw, STAR_IN_NAME_GRAY)
            return

        if not name_tokens:
            self._handle_date_only_line(line_no, raw, ranges, singles, times)
            return

        # 交通行优先（`->` + 两端点）：即使无时刻也是交通段（如 @纯阳观 -> @宽窄巷子 徒步）
        if "->" in raw and len(split_transport(raw)) == 2:
            self._make_transport(line_no, raw, ranges, singles, times)
            self._seen_event = True
            return

        # 事件信号 = 行上有显式时刻 / 日期（或日期区间）；否则按城市行处理
        if not times and not ranges and not singles:
            for t in name_tokens:
                self._add_city(t.text, line_no, raw)
            return

        self._make_visit(line_no, raw, tokens, ranges, singles, times)
        self._seen_event = True

    # ------------------------------------------------------------ 仅日期行

    def _handle_date_only_line(
        self,
        line_no: int,
        raw: str,
        ranges: list[tuple[int, int, DateRange]],
        singles: list[tuple[int, int, DatePart]],
        times: list[tuple[int, int, str]],
    ) -> None:
        has_hm = bool(times)
        if ranges and not has_hm:
            # 无 @ 地名的日粒度区间（无 HH:MM）→ trip 区间候选；须在便签顶部/首事件前
            r = ranges[0][2]
            start, s_ok = self.resolver.resolve(r.start)
            end, e_ok = self.resolver.resolve(r.end)
            if s_ok and e_ok and not self._seen_trip_range and not self._seen_event:
                self.trip_range = {
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "start_local": local_iso(start),
                    "end_local": local_iso(end),
                    "raw": raw.strip(),
                }
                self._seen_trip_range = True
                self.resolver.set_from_date(start)
                return
            self._add_gray(line_no, raw, TRIP_RANGE_GRAY)
            return
        if not has_hm and len(singles) == 1:
            # 单个日期 → 日期标记，仅更新上下文（§2.3 日期状态继承），不产事件
            part = singles[0][2]
            _d, ok = self.resolver.resolve(part)
            if ok:
                self.resolver.set_explicit(part)
                return
            self._add_gray(line_no, raw, DEFER_GRAY)  # 无上下文补齐（如 @2号 缺年月）→ 交校正页
            return
        self._add_gray(line_no, raw, DEFER_GRAY)

    # ------------------------------------------------------------ 事件：交通段

    def _make_transport(
        self,
        line_no: int,
        raw: str,
        ranges: list[tuple[int, int, DateRange]],
        singles: list[tuple[int, int, DatePart]],
        times: list[tuple[int, int, str]],
    ) -> None:
        halves = split_transport(raw)
        from_text = _endpoint_text(halves[0])
        to_text = _endpoint_text(halves[1])
        half_times = [scan_times(h) for h in halves]
        depart_hm = half_times[0][0][2] if half_times[0] else None
        arrive_hm = half_times[1][0][2] if len(half_times) > 1 and half_times[1] else None

        # 出发/到达日期：行内显式日期优先（双日期时两端各自取用），否则继承状态
        date_parts = [p for _, _, p in singles] or ([ranges[0][2].start] if ranges else [])

        def _day(part: DatePart | None) -> date | None:
            if part is not None:
                d, ok = self.resolver.resolve(part)
                if ok:
                    return d
            return self.resolver.current_date()

        day_depart = _day(date_parts[0] if date_parts else None)
        day_arrive = _day(date_parts[-1] if len(date_parts) >= 2 else None) or day_depart
        if day_arrive is not None:
            self.resolver.set_from_date(day_arrive)

        stripped = self._strip_structure(raw, ranges, singles, times, None)
        mode_candidate = closed.find_mode(stripped)
        review = stripped
        if mode_candidate:  # 交通方式既已剥为候选，review 不再重复携带该词
            review = re.sub(r"\s+", " ", stripped.replace(mode_candidate, "", 1)).strip()
        ev: dict[str, Any] = {
            "kind": "transport",
            "line_no": line_no,
            "raw": raw.strip(),
            "flags": ["疑似交通"],
            "from_text": from_text or "",
            "to_text": to_text or "",
            "depart_local": local_iso(day_depart, depart_hm) if (day_depart and depart_hm) else None,
            "arrive_local": local_iso(day_arrive, arrive_hm) if (day_arrive and arrive_hm) else None,
            "needs_date": day_depart is None and depart_hm is not None,
            "mode_candidate": mode_candidate,
            "review": review,
        }
        if from_text is None or to_text is None:
            ev["flags"].append("交通端点缺失")
        self.events.append(ev)
        self._open_event = len(self.events) - 1

    # ------------------------------------------------------------ 事件：visit

    def _make_visit(
        self,
        line_no: int,
        raw: str,
        tokens: list[AtToken],
        ranges: list[tuple[int, int, DateRange]],
        singles: list[tuple[int, int, DatePart]],
        times: list[tuple[int, int, str]],
    ) -> None:
        names = [t.text for t in tokens if _is_name_token(t)]
        primary = names[0]
        for extra in names[1:]:
            self._add_city(extra, line_no, raw)

        day = self._event_day(ranges, singles)
        if day is not None:
            self.resolver.set_from_date(day)
        first_hm_end = times[0][1] if times else 0
        rating, s_start, s_end = closed.strip_rating(raw, first_hm_end)

        flags: list[str] = []
        stripped = self._strip_structure(
            raw, ranges, singles, times, (s_start, s_end) if s_start >= 0 else None
        )
        mode_candidate = closed.find_mode(stripped)
        # 疑似轨迹：关系词提示 + 运动类交通/活动词（徒步/骑行）
        is_trail = closed.has_trail_hint(raw) or mode_candidate in ("徒步", "骑行")
        if is_trail:
            flags.append("疑似轨迹")
        label_hint: str | None = None
        if is_trail:
            if mode_candidate in ("徒步", "骑行"):
                label_hint = mode_candidate
            elif any(w in raw for w in ("登顶", "爬山")):
                label_hint = "爬山"

        ev: dict[str, Any] = {
            "kind": "visit",
            "line_no": line_no,
            "raw": raw.strip(),
            "flags": flags,
            "name": primary,
            "at_local": local_iso(day, times[0][2]) if (day and times) else (local_iso(day) if day else None),
            "needs_date": day is None,
            "rating_candidate": rating,
            "review": stripped,
            "mode_candidate": mode_candidate,
            "label_hint": label_hint,
        }
        self.events.append(ev)
        self._open_event = len(self.events) - 1

    # ------------------------------------------------------------ 共用

    def _event_day(
        self,
        ranges: list[tuple[int, int, DateRange]],
        singles: list[tuple[int, int, DatePart]],
    ) -> date | None:
        """事件日期：行内显式日期优先（区间用起点），否则当前继承状态。"""
        if ranges:
            d, ok = self.resolver.resolve(ranges[0][2].start)
            if ok:
                return d
        if singles:
            d, ok = self.resolver.resolve(singles[0][2])
            if ok:
                return d
        return self.resolver.current_date()

    def _strip_structure(
        self,
        raw: str,
        ranges: list[tuple[int, int, DateRange]],
        singles: list[tuple[int, int, DatePart]],
        times: list[tuple[int, int, str]],
        star: tuple[int, int] | None,
    ) -> str:
        """剥除结构位（@标记、日期/时刻、星级、关系词），剩余为评价正文候选。"""
        spans: list[tuple[int, int]] = []
        for t in lex_at(raw):
            spans.append((t.at, t.end))
        for s, e, _r in (*ranges, *singles):
            spans.append((s, e))
        for s, e, _v in times:
            spans.append((s, e))
        if star is not None:
            spans.append(star)
        for m in _RELATION_SPANS.finditer(raw):
            spans.append((m.start(), m.end()))
        spans.sort()

        out: list[str] = []
        pos = 0
        for s, e in spans:
            if s > pos:
                out.append(raw[pos:s])
            pos = max(pos, e)
        out.append(raw[pos:])
        return re.sub(r"\s+", " ", "".join(out)).strip()

    def _add_city(self, name: str, line_no: int, raw: str) -> None:
        if name and not any(c["name"] == name for c in self.cities):
            self.cities.append({"name": name, "line_no": line_no, "raw": raw.strip()})

    def _add_gray(self, line_no: int, raw: str, reason: str) -> None:
        self.gray.append({"line_no": line_no, "raw": raw.strip(), "reason": reason})


def _is_name_token(t: AtToken) -> bool:
    """token 是地名快照（非日期）：不含纯日期片段，且整个 token 不是一段日期区间。"""
    if parse_date_piece(t.text) is not None:
        return False
    ranges, singles = scan_dates(t.text)
    if any(s == 0 and e == len(t.text) for s, e, _ in ranges):
        return False
    return not any(s == 0 and e == len(t.text) for s, e, _ in singles)


def _endpoint_text(half: str) -> str | None:
    """取交通行半段的端点：优先 @ 名称 token；缺失时按 -> 上下文尽力恢复（草案 §2.4 裂缝 4）。"""
    if not half.strip():
        return None
    for t in lex_at(half):
        if _is_name_token(t):
            return t.text
    m = re.match(r"\s*(\S+)", half)
    if not m:
        return None
    candidate = m.group(1)
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
        return None  # 恢复出的『端点』其实是时刻 → 判缺失
    if parse_date_piece(candidate) is not None:
        return None
    return candidate