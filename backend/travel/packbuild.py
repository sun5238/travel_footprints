"""PBF→区域路网包构建工具（M4 路书 Pi，ADR-0008）。

构建时可选在线：用户先自取 OSM PBF extract（Geofabrik / BBBike，免费无账号），
再在本地用本工具构建成区域路网包（JSON）。pyrosm 是**构建时**依赖，本模块惰性
导入——不装 pyrosm 时运行时完全不受影响（store 惰性加载包）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .routing import RouteEdge, RoutingGraph, haversine_km, save_pack

# OSM highway 标签 → 路由类别（与 routing._BASE_WEIGHT 对齐；None = 不参与路由）
_HIGHWAY_TO_CATEGORY: dict[str, str] = {
    "motorway": "motorway", "motorway_link": "motorway",
    "trunk": "trunk", "trunk_link": "trunk",
    "primary": "primary", "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary",
    "residential": "residential", "unclassified": "residential",
    "living_street": "residential",
    "service": "service",
    "cycleway": "cycleway",
    "path": "path",
    "track": "track", "track_grade1": "track", "track_grade2": "track", "track_grade3": "track",
    "footway": "footway", "pedestrian": "footway",
}

_ONE_WAY_FORWARD = {"yes", "true", "1"}
_ONE_WAY_REVERSE = {"-1", "reverse"}


def classify_highway(tag: str | None) -> str | None:
    """OSM highway 标签 → 路由类别（未知/不参与路由返回 None）。"""
    tag = (tag or "").strip()
    return _HIGHWAY_TO_CATEGORY.get(tag)


def _line_distance_m(geometry: Any) -> float | None:
    """取线几何首尾点的大圆距离作边里程（区域尺度够用）。"""
    try:
        coords = list(geometry.coords)
        if len(coords) < 2:
            return None
        (lng1, lat1) = coords[0]
        (lng2, lat2) = coords[-1]
        return round(haversine_km(lat1, lng1, lat2, lng2) * 1000.0, 1)
    except (AttributeError, TypeError, ValueError):
        return None


def pbf_to_graph(pbf_path: Path) -> RoutingGraph:
    """读 OSM PBF → RoutingGraph。pyrosm 未装时给出清晰指引。"""
    try:
        import pyrosm  # type: ignore[import-not-found]  # noqa: F401  (构建时依赖，惰性导入)
    except ImportError as exc:
        raise ValueError(
            "构建路网包需要 pyrosm（构建时依赖）："
            "./scripts/build-routing-pack.sh 会自动安装；"
            "或 pip install --target .pylibs -r backend/requirements-build.txt"
        ) from exc

    osm = pyrosm.OSM(str(pbf_path))
    nodes_df = osm.get_nodes()
    net = osm.get_network()

    try:
        node_map: dict[int, tuple[float, float]] = {}
        for _, row in nodes_df.iterrows():
            node_map[int(row["id"])] = (float(row["lat"]), float(row["lon"]))
    except (KeyError, TypeError) as exc:
        raise ValueError("PBF 节点表缺少 id/lat/lon 列") from exc

    graph = RoutingGraph()
    for node_id, (lat, lng) in node_map.items():
        graph.add_node(node_id, lat, lng)

    required = {"from_node", "to_node", "highway"}
    missing = required - set(net.columns)
    if missing:
        raise ValueError(f"PBF 网络表缺少列: {sorted(missing)}")

    for _, row in net.iterrows():
        category = classify_highway(row.get("highway"))
        if category is None:
            continue
        distance_m = _line_distance_m(row.get("geometry"))
        if distance_m is None:
            continue
        a = int(row["from_node"])
        b = int(row["to_node"])
        if a not in graph.nodes or b not in graph.nodes:
            continue
        oneway = row.get("oneway")
        oneway_str = str(oneway).strip().lower() if oneway is not None else ""
        if oneway_str in _ONE_WAY_REVERSE:
            graph.add_edge(b, RouteEdge(a, distance_m, category))
        elif oneway_str in _ONE_WAY_FORWARD:
            graph.add_edge(a, RouteEdge(b, distance_m, category))
        else:
            graph.add_edge(a, RouteEdge(b, distance_m, category))
            graph.add_edge(b, RouteEdge(a, distance_m, category))
    return graph


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description="构建区域路网包（OSM PBF → JSON 包）")
    ap.add_argument("--pbf", required=True, help="OSM PBF extract 路径（Geofabrik/BBBike）")
    ap.add_argument(
        "--out",
        default="routing/pack.json",
        help="输出区域路网包路径（默认 routing/pack.json，放数据根下）",
    )
    args = ap.parse_args(argv)

    graph = pbf_to_graph(Path(args.pbf))
    out = save_pack(graph, Path(args.out))
    print(
        f"区域路网包写出: {out}  节点 {len(graph.nodes)}，边 "
        f"{sum(len(es) for es in graph.adj.values())}"
    )


if __name__ == "__main__":
    main()