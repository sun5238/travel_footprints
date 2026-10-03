"""GPX 1.1 导出（M4 路书 S5）。

路书导出用 `<rte>`（路线，导航软件友好；两步路/OsmAnd/Garmin/高德可导入）。
只导出有坐标的途经点（无坐标点仅作标注，不入 GPX）。
"""

from __future__ import annotations

from typing import Any

_XML_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"}


def _escape_xml(text: str) -> str:
    return "".join(_XML_ESC.get(ch, ch) for ch in text)


def routebook_to_gpx(name: str, points: list[dict[str, Any]]) -> str:
    """生成 GPX 1.1，含单条 `<rte>` 与全部有坐标途经点（[起点…终点] 顺序）。"""
    located = [p for p in points if p.get("lat") is not None and p.get("lng") is not None]
    rtepts = "\n".join(
        f'      <rtept lat="{p["lat"]:.6f}" lon="{p["lng"]:.6f}">'
        f'<name>{_escape_xml(p.get("name") or "")}</name></rtept>'
        for p in located
    )
    ns = "http://www.topografix.com/GPX/1/1"
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<gpx version="1.1" creator="Travel Footprints" xmlns="{ns}">',
            "  <rte>",
            f"    <name>{_escape_xml(name)}</name>",
            rtepts,
            "  </rte>",
            "</gpx>",
        ]
    )