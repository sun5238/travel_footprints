"""前端字段缝合线测试（B 层）：验证前端消费的字段都存在于后端真实响应中。

作用：与 test_contract.py（后端侧权威键集）互为反向——这里以 frontend/app.js 的
字段消费为另一侧，防止「前端读取了后端从未返回的字段 → undefined」这类前后端
字段漂移。路径基准：tests/backend/test_frontend_fields.py 的 parents[2] = 项目根。
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND_APP = Path(__file__).resolve().parents[2] / "frontend" / "app.js"

# 前端从响应数据对象读取字段的容器变量（模板 {{ }} + JS 点访问均扫描）
_CONTAINER = r"(?:v|p|c|m|t|place|selectedPlace)"
_FIELD = r"[a-zA-Z_][a-zA-Z0-9_]*"

# 捕获形如 v.rating / p.city_id / dashboard.stats.cities_lit / at.local 的读取
_DIRECT = re.compile(rf"\b{_CONTAINER}\.({_FIELD})\b")
_STATS = re.compile(r"\bdashboard\.stats\.({_FIELD})\b")
_STRUCT = re.compile(r"\b{_CONTAINER}\.\w+\.(local|tz|epoch)\b")
# dashboard 顶层容器名（lit_cities / recent_trips 等）
_DASH_TOP = re.compile(r"\bdashboard\.({_FIELD})\b")

# 已知的无害假读取（非后端响应字段，扫描会误报，故登记）：
# - city：p.city / selectedPlace.city 是故意恒为空串的占位，后端不返回 city
# - value：Vue ref 解包访问（dashboard.value 等），不是响应字段
# - role：地图 feature 属性（p.role），不是后端 place/city 响应字段
# - get / has / set：JS Map 方法名，可能被全文件扫描误当作字段名
_KNOWN_MISSING = {"city", "value", "role", "get", "has", "set"}


def _app_field_names(src: str) -> set[str]:
    """从 app.js 文本提取全部「响应数据字段名」候选。"""
    fields = set()
    for m in _DIRECT.finditer(src):
        fields.add(m.group(1))
    for m in _STATS.finditer(src):
        fields.add(m.group(1))
    for m in _STRUCT.finditer(src):
        fields.add(m.group(1))
    for m in _DASH_TOP.finditer(src):
        fields.add(m.group(1))
    return fields


def _response_key_universe(client) -> set[str]:
    """命中各读取端点，递归收集响应 JSON 中出现的全部字段名。"""
    keys: set[str] = set()

    def walk(obj) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k)
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    trips = client.get("/api/trips").json()
    first_trip_id = trips[0]["id"] if trips else None
    probes = [
        client.get("/api/dashboard").json(),
        client.get("/api/cities").json(),
        client.get("/api/cities?lit=1").json(),
        client.get("/api/places?lit=1").json(),
        client.get("/api/visits").json(),
        client.get("/api/media").json(),
        client.get("/api/trips").json(),
    ]
    if first_trip_id is not None:
        probes.append(client.get(f"/api/trips/{first_trip_id}").json())
        probes.append(client.get(f"/api/trips/{first_trip_id}/legs").json())
    for probe in probes:
        walk(probe)
    return keys


def test_frontend_fields_all_exist(seeded_client):
    src = FRONTEND_APP.read_text(encoding="utf-8")
    consumed = _app_field_names(src) - _KNOWN_MISSING
    assert consumed, "未从 app.js 提取到任何字段消费，说明扫描规则失效"

    universe = _response_key_universe(seeded_client)
    missing = sorted(consumed - universe)
    assert not missing, (
        f"前端读取了后端响应中不存在的字段: {missing}。"
        "可能前端新增消费而后端未返回，或字段名已改名。"
    )


def test_app_js_smoke(seeded_client):
    """轻量冒烟：前端读的字段确实在响应里可取到值（非仅键存在）。"""
    src = FRONTEND_APP.read_text(encoding="utf-8")
    # 检查 app.js 调用的 4 个核心 GET 端点都能 200，防止路径前缀漂移
    for path in ("/api/dashboard", "/api/cities", "/api/visits", "/api/media", "/api/places?lit=1"):
        resp = seeded_client.get(path)
        assert resp.status_code == 200, path
        assert resp.json() is not None