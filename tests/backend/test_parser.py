"""解析器纯函数测试：只切不认内核（main.py 不涉及，直接测 parser 包）。

时间推算注入固定 now（2026-10-01），保证缺年/继承行为确定。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from travel.config import DEFAULT_TIMEZONE
from travel.parser import parse_text


def _parse(text: str, tz: str = DEFAULT_TIMEZONE) -> dict:
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=ZoneInfo(tz))
    return parse_text(text, tz=tz, now=now)


# ---------------------------------------------------------------- 权威示例

AUTHORITATIVE = """\
# 国庆成都行
@2026-10-01 ~ 2026-10-07
高铁票要提前一周抢
@重庆 @成都
@重庆北 08:30 -> @成都东 11:00 高铁
@宽窄巷子 14:20 5星 人很多，盖章和糖画有意思
（青羊宫店附近，人特别多）
@陈麻婆豆腐 19:30 4星 麻婆豆腐很下饭，服务一般
@青城山 08:00 - 11:20 登顶 - 16:30 结束
"""


def test_authoritative_example():
    draft = _parse(AUTHORITATIVE)
    assert draft["title"] == "国庆成都行"
    assert draft["note"] == "高铁票要提前一周抢"
    assert draft["trip_range"] == {
        "start_date": "2026-10-01",
        "end_date": "2026-10-07",
        "start_local": "2026-10-01T00:00:00",
        "end_local": "2026-10-07T00:00:00",
        "raw": "@2026-10-01 ~ 2026-10-07",
    }
    assert [c["name"] for c in draft["cities"]] == ["重庆", "成都"]
    assert draft["gray"] == []

    events = draft["events"]
    # 交通行
    t = events[0]
    assert t["kind"] == "transport"
    assert t["from_text"] == "重庆北" and t["to_text"] == "成都东"
    assert t["depart_local"] == "2026-10-01T08:30:00"
    assert t["arrive_local"] == "2026-10-01T11:00:00"
    assert t["mode_candidate"] == "高铁"
    assert "疑似交通" in t["flags"]
    # 两条普通 visit
    v1, v2 = events[1], events[2]
    assert v1["kind"] == "visit" and v1["name"] == "宽窄巷子"
    assert v1["at_local"] == "2026-10-01T14:20:00" and v1["rating_candidate"] == 5
    assert v1["review"] == "人很多，盖章和糖画有意思 （青羊宫店附近，人特别多）"  # 续行归并
    assert v1["needs_date"] is False
    assert v2["kind"] == "visit" and v2["name"] == "陈麻婆豆腐"
    assert v2["at_local"] == "2026-10-01T19:30:00" and v2["rating_candidate"] == 4
    assert v2["review"] == "麻婆豆腐很下饭，服务一般"
    # 轨迹行并入 visit，带疑似轨迹提示与 label 提示
    trail = events[3]
    assert trail["kind"] == "visit" and trail["name"] == "青城山"
    assert trail["at_local"] == "2026-10-01T08:00:00"
    assert "疑似轨迹" in trail["flags"]
    assert trail["label_hint"] == "爬山"
    assert "登顶" in trail["review"]


# ---------------------------------------------------------------- 切行分类

def test_blank_line_ignored():
    draft = _parse("@成都\n\n@重庆\n")
    assert [c["name"] for c in draft["cities"]] == ["成都", "重庆"]


def test_continuation_before_event_becomes_trip_note():
    draft = _parse("@2026-10-01 ~ 2026-10-07\n高铁票要提前一周抢\n@宽窄巷子 14:20")
    assert draft["note"] == "高铁票要提前一周抢"


def test_title_without_space_after_hash():
    assert _parse("#国庆成都行")["title"] == "国庆成都行"


def test_second_title_ignored():
    draft = _parse("# 第一次\n# 第二次\n")
    assert draft["title"] == "第一次"


# ---------------------------------------------------------------- @ 词法

def test_at_gets_up_to_one_whitespace():
    draft = _parse("@ 成都 @重庆")
    assert [c["name"] for c in draft["cities"]] == ["成都", "重庆"]


def test_name_swallowing_star_goes_gray():
    draft = _parse("@陈麻婆豆腐4星 19:00")
    assert draft["events"] == []
    assert draft["gray"] and "星级" in draft["gray"][0]["reason"]


def test_legit_name_with_leading_cn_digit_not_flagged():
    # 「五星饭店」是合法名（token 不以星结尾），不应误判为吞星
    draft = _parse("@五星饭店 18:00")
    assert draft["gray"] == []
    assert draft["events"][0]["name"] == "五星饭店"


def test_multi_at_no_time_each_city():
    draft = _parse("@重庆 @成都")
    assert [c["name"] for c in draft["cities"]] == ["重庆", "成都"]


def test_city_dedupe_by_name():
    draft = _parse("@成都\n@成都\n")
    assert len(draft["cities"]) == 1


def test_unmarked_line_start_place_is_continuation():
    # 无宽容路径：忘写 @ 的地名按续行归并，不恢复为地名
    draft = _parse("@成都\n春熙路 14:20 人很多\n")
    assert draft["events"] == []
    assert draft["note"] == "春熙路 14:20 人很多"


def test_date_inside_one_at_token_is_range():
    # @2026-10-01至2026-10-07：`至` 不是 token 边界，但整 token 是日期区间
    draft = _parse("@2026-10-01至2026-10-07\n@宽窄巷子 14:20")
    assert draft["trip_range"]["start_date"] == "2026-10-01"
    assert draft["trip_range"]["end_date"] == "2026-10-07"
    assert draft["events"][0]["at_local"] == "2026-10-01T14:20:00"


# ---------------------------------------------------------------- 时间语法

def test_trip_range_inclusive_end_day():
    draft = _parse("@2026-10-01 至 2026-10-07\n")
    r = draft["trip_range"]
    assert r["end_date"] == "2026-10-07" and r["end_local"] == "2026-10-07T00:00:00"


def test_range_with_cn_yearless_dates():
    draft = _parse("@10月1号 ~ 10月7号\n@重庆 14:00")
    assert draft["trip_range"]["start_date"] == "2026-10-01"
    assert draft["trip_range"]["end_date"] == "2026-10-07"
    assert draft["events"][0]["at_local"] == "2026-10-01T14:00:00"


def test_full_date_in_event_line():
    draft = _parse("@宽窄巷子 2026-10-02 14:20 5星 好")
    ev = draft["events"][0]
    assert ev["at_local"] == "2026-10-02T14:20:00"
    assert ev["rating_candidate"] == 5


def test_cn_month_day_in_event_line():
    draft = _parse("@2026-10-01 ~ 2026-10-07\n@宽窄巷子 10月2号 14:20")
    assert draft["events"][0]["at_local"] == "2026-10-02T14:20:00"


def test_day_only_inherits_from_trip_context():
    # @2号 作日期标记 → 后续事件继承 2号（月/年自 trip 区间补齐）
    draft = _parse("@2026-10-01 ~ 2026-10-07\n@2号\n@宽窄巷子 14:00")
    assert draft["events"][0]["at_local"] == "2026-10-02T14:00:00"
    assert draft["events"][0]["needs_date"] is False
    assert draft["gray"] == []


def test_day_only_without_month_context_goes_gray():
    draft = _parse("@2号")
    assert draft["gray"]  # 无上下文补齐 → 标灰


def test_date_marker_updates_context():
    draft = _parse("@10月2号\n@宽窄巷子 14:20")
    assert draft["events"][0]["at_local"] == "2026-10-02T14:20:00"
    assert draft["gray"] == []


def test_event_without_any_date_is_needs_date():
    draft = _parse("@宽窄巷子 14:20")
    ev = draft["events"][0]
    assert ev["at_local"] is None and ev["needs_date"] is True


def test_trip_range_mid_note_is_gray():
    draft = _parse("@重庆 14:00\n@2026-10-01 ~ 2026-10-07\n")
    assert draft["events"] and draft["gray"] and "区间" in draft["gray"][0]["reason"]


def test_malformed_time_not_stripped():
    # 16:75 非法 → 无时刻信号，整行走城市行（只切不认，不猜）
    draft = _parse("@宽窄巷子 16:75 好")
    assert draft["events"] == []
    assert draft["cities"] and draft["cities"][0]["name"] == "宽窄巷子"


# ---------------------------------------------------------------- 星级剥离

def test_star_not_right_after_time_not_stripped():
    # 人很多 与 5星 之间有评价文字 → 非紧贴，不剥
    draft = _parse("@宽窄巷子 14:20 人很多 5星 好")
    assert draft["events"][0]["rating_candidate"] is None


def test_star_embedded_in_word_not_stripped():
    draft = _parse("@宽窄巷子 14:20 5星大厨掌勺")
    assert draft["events"][0]["rating_candidate"] is None


def test_cn_digit_star():
    draft = _parse("@火锅店 12:00 五星 好吃")
    assert draft["events"][0]["rating_candidate"] == 5


def test_star_symbol():
    draft = _parse("@火锅店 12:00 ★5 好吃")
    assert draft["events"][0]["rating_candidate"] == 5


def test_only_one_star_stripped_per_line():
    draft = _parse("@火锅店 12:00 5星 4星分店多")
    ev = draft["events"][0]
    assert ev["rating_candidate"] == 5
    assert "4星" in ev["review"]


# ---------------------------------------------------------------- 交通

def test_transport_endpoint_missing_recovered():
    # 单端漏 @ ：按 -> 上下文尽力恢复
    draft = _parse("@重庆北 08:30 -> 成都东 11:00 高铁")
    ev = draft["events"][0]
    assert ev["kind"] == "transport"
    assert ev["from_text"] == "重庆北" and ev["to_text"] == "成都东"
    assert "交通端点缺失" not in ev["flags"]


def test_transport_endpoint_unrecoverable_flagged():
    draft = _parse("@重庆北 08:30 -> 11:00 高铁")
    ev = draft["events"][0]
    assert ev["from_text"] == "重庆北" and ev["to_text"] == ""
    assert "交通端点缺失" in ev["flags"]


def test_transport_no_at_all_is_continuation():
    # 全量必 @：无 @ 的交通行按续行归并，不恢复为 transport
    draft = _parse("@成都\n重庆北 08:30 -> 成都东 11:00 高铁")
    assert draft["events"] == []
    assert "重庆北 08:30" in draft["note"]


def test_walking_transport_without_times():
    draft = _parse("@纯阳观 -> @宽窄巷子")
    ev = draft["events"][0]
    assert ev["kind"] == "transport"
    assert ev["from_text"] == "纯阳观" and ev["to_text"] == "宽窄巷子"
    assert ev["depart_local"] is None


# ---------------------------------------------------------------- 轨迹 hint

def test_trail_hint_words_and_label():
    draft = _parse("@青城山 08:00 - 11:20 登顶 - 16:30 结束")
    ev = draft["events"][0]
    assert "疑似轨迹" in ev["flags"]
    assert ev["label_hint"] == "爬山"


def test_trail_hint_via_mode():
    draft = _parse("@青城山 08:00 徒步到山顶")
    ev = draft["events"][0]
    assert "疑似轨迹" in ev["flags"]
    assert ev["label_hint"] == "徒步"


# ---------------------------------------------------------------- 城市/事件判别

def test_city_line_with_time_becomes_event_and_extra_city():
    draft = _parse("@重庆 @成都 14:20")
    ev = draft["events"][0]
    assert ev["kind"] == "visit" and ev["name"] == "重庆"
    assert [c["name"] for c in draft["cities"]] == ["成都"]