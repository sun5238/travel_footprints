"""导航交接纯函数（M4 路书 S7，ADR-0008）。

三选一：一键深链 / 起终点导航 / 文本复制。深链均为「在线动作」——本模块只构造 URL，
是否触网由调用方（前端）显式确认后执行。

注意：腾讯 routeplan 的 `mode` 与 `via` 参数确切的字段名/取值请以官方文档为准；
这里按路书产品的合约构造，参数集中在此便于按文档微调。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

_TENCENT_MODE = {"driving": "driving", "cycling": "riding", "walking": "walking"}
# 高德导航 URI 无骑行模式（事实，见 ADR-0008）
_AMAP_MODE = {"driving": "driving", "walking": "walking"}


def _coord_str(p: dict[str, Any]) -> str:
    return f"{p['lat']:.6f},{p['lng']:.6f}"


def _qs(params: list[tuple[str, str]]) -> str:
    def safe(v: str) -> str:
        return quote(v, safe=",;")

    return "&".join(f"{k}={safe(v)}" for k, v in params)


def nav_links(
    name: str,
    mode: str,
    points: list[dict[str, Any]],
    referer: str = "travel-footprints",
) -> dict[str, Any]:
    """按模式构造交接三件套：tencent / amap 深链 + text 兜底。

    - 只取有坐标点构造深链；无坐标点不参与导航 URL，但保留在文本兜底里。
    - 起终点 = 首/末有坐标点；途经 = 中间有坐标点。
    """
    located = [p for p in points if p.get("lat") is not None and p.get("lng") is not None]
    start = located[0] if located else None
    end = located[-1] if len(located) >= 2 else None
    vias = located[1:-1] if len(located) >= 3 else []

    tencent: str | None = None
    t_mode = _TENCENT_MODE.get(mode)
    if t_mode is not None and start is not None and end is not None:
        params = [("mode", t_mode), ("from", _coord_str(start)), ("to", _coord_str(end))]
        if vias:
            params.append(("via", ";".join(_coord_str(v) for v in vias)))
        params.append(("referer", referer))
        tencent = "https://apis.map.qq.com/uri/v1/routeplan?" + _qs(params)

    amap: str | None = None
    a_mode = _AMAP_MODE.get(mode)
    if a_mode is not None and start is not None and end is not None:
        params = [("mode", a_mode), ("to", _coord_str(end)), ("toName", end.get("name") or "")]
        amap = "https://uri.amap.com/navigation?" + _qs(params)

    lines: list[str] = []
    for i, p in enumerate(points):
        role = "起点" if i == 0 else ("终点" if i == len(points) - 1 else "途经")
        coord = _coord_str(p) if p.get("lat") is not None and p.get("lng") is not None else "（无坐标）"
        lines.append(f"{role}：{p.get('name') or ''} {coord}")

    return {"tencent": tencent, "amap": amap, "text": "\n".join(lines)}