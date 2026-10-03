"""路书 zip 打包/解包（M4 路书 S6）。

布局：manifest.json（元数据 + 途经点/停靠打标）+ route.geojson（线几何，有则写）。
导入语义：只新建、不覆盖（同名也新增一本，用户可改名，ADR-0008）。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

_POINT_FIELDS = ("name", "lat", "lng", "pos_kind", "stop_type", "stop_name", "stop_note")
_STOP_FIELDS = ("name", "lat", "lng", "pos_kind", "stop_type", "stop_note")


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {k: source.get(k) for k in fields}


def write_routebook_zip(book: dict[str, Any], dest: Path) -> Path:
    """把路书详情 dict 写成一个自包含 zip。"""
    manifest = {
        "app": "travel-footprints",
        "kind": "routebook",
        "name": book["name"],
        "mode": book["mode"],
        "preset": book["preset"],
        "mileage_km": book["mileage_km"],
        "mileage_manual": bool(book["mileage_manual"]),
        "geometry_source": book["geometry"]["source"],
        "points": [_pick(p, _POINT_FIELDS) for p in book["points"]],
        "stops": [_pick(s, _STOP_FIELDS) for s in book["stops"]],
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        line = book["geometry"]["geojson"]
        if line is not None:
            zf.writestr("route.geojson", json.dumps(line, ensure_ascii=False))
    return dest


def read_routebook_zip(zip_path: Path) -> dict[str, Any]:
    """解包路书包 → 可直接 create_routebook 的字段。损坏/缺元数据即报错。"""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise ValueError("路书包缺少 manifest.json")
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("kind") != "routebook":
            raise ValueError("不是路书包")
        name = manifest.get("name")
        if not name:
            raise ValueError("路书包缺少名称")
        data: dict[str, Any] = {
            "name": name,
            "mode": manifest.get("mode") or "driving",
            "preset": manifest.get("preset") or "balanced",
            "mileage_km": manifest.get("mileage_km"),
            "mileage_manual": bool(manifest.get("mileage_manual", False)),
            "geometry_source": manifest.get("geometry_source") or "engine",
            "points": manifest.get("points") or [],
            "stops": manifest.get("stops") or [],
        }
        if "route.geojson" in names:
            data["geometry_json"] = zf.read("route.geojson").decode("utf-8")
    return data