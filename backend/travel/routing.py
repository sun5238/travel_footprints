"""M4 路书：进程内轻量路由（S2 纯函数）。

决策见 ADR-0008：运行时自建路由（自管边权 + A*），引擎抽象层可切 Valhalla。
本模块只依赖「路由图」结构（RoutingGraph），不依赖 pyrosm/osmium——那属于
PBF→路网构建工具切片（构建时可选在线，另行确认依赖）。
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any

# 类别基础系数（权重 = 距离km × 系数；系数越小越偏好）。
# None = 该模式禁行此类路（高速/主干道对骑行/徒步）。
_BASE_WEIGHT: dict[str, dict[str, float | None]] = {
    "driving": {
        "motorway": 0.7, "trunk": 0.9, "primary": 1.0, "secondary": 1.1,
        "tertiary": 1.2, "residential": 1.6, "service": 2.0, "cycleway": 3.0,
        "path": 4.0, "track": 3.0, "footway": 4.0,
    },
    "cycling": {
        "motorway": None, "trunk": None, "primary": 3.0, "secondary": 1.6,
        "tertiary": 1.2, "residential": 1.0, "service": 1.0, "cycleway": 0.5,
        "path": 0.6, "track": 0.7, "footway": 0.7,
    },
    "walking": {
        "motorway": None, "trunk": None, "primary": None, "secondary": 1.6,
        "tertiary": 1.5, "residential": 1.0, "service": 1.2, "cycleway": 0.8,
        "path": 0.6, "track": 0.6, "footway": 0.5,
    },
}

# 档位系数（作用于类别之上）。未列出的类别不受影响。
_PRESET_MULT: dict[str, dict[str, dict[str, float]]] = {
    "driving": {
        "balanced": {},
        "fast": {
            "motorway": 0.6, "trunk": 0.7, "secondary": 1.2, "tertiary": 1.2,
            "residential": 1.4,
        },
        "scenic": {
            "motorway": 1.2, "trunk": 1.2, "secondary": 0.85, "tertiary": 0.85,
            "residential": 0.9,
        },
    },
    "cycling": {
        "balanced": {},
        "greenway": {
            "cycleway": 0.5, "path": 0.6, "track": 0.7, "secondary": 1.2, "primary": 1.4,
        },
        "fast": {
            "secondary": 0.8, "tertiary": 0.8, "residential": 0.85, "cycleway": 1.1,
        },
    },
    "walking": {
        "balanced": {},
        "offroad": {
            "path": 0.6, "track": 0.6, "residential": 1.3, "secondary": 1.4, "primary": 1.5,
        },
        "fast": {
            "residential": 0.8, "tertiary": 0.8, "service": 0.85, "path": 1.2,
        },
    },
}

# 自驾「走风景多」：边中点在景点半径内则整体折扣
_POI_RADIUS_KM = 4.0
_POI_BONUS = 0.5

_KM_PER_DEG = 111.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点大圆距离 km（GeoJSON 是 [lng, lat]，这里接 (lat, lng)）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class RouteEdge:
    """一条有向边；无向路线建模为 A→B、B→A 两条。"""

    target: int
    distance_m: float
    category: str


class RoutingGraph:
    """轻量路网图（运行时契约；真实图来自区域路网包构建工具，见 ADR-0008）。"""

    def __init__(self) -> None:
        self.nodes: dict[int, tuple[float, float]] = {}
        self.adj: dict[int, list[RouteEdge]] = {}

    def add_node(self, nid: int, lat: float, lng: float) -> None:
        self.nodes[nid] = (lat, lng)
        self.adj.setdefault(nid, [])

    def add_edge(self, frm: int, edge: RouteEdge) -> None:
        self.adj.setdefault(frm, []).append(edge)


def _edge_cost(
    graph: RoutingGraph,
    frm: int,
    edge: RouteEdge,
    mode: str,
    preset: str,
    pois: list[tuple[float, float]] | None,
) -> float | None:
    base = _BASE_WEIGHT.get(mode, {}).get(edge.category)
    if base is None:
        return None  # 该模式禁行此类别
    w = base * _PRESET_MULT.get(mode, {}).get(preset, {}).get(edge.category, 1.0)
    if pois and mode == "driving" and preset == "scenic":
        a = graph.nodes[frm]
        b = graph.nodes[edge.target]
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        for pl, pn in pois:
            if haversine_km(mid[0], mid[1], pl, pn) <= _POI_RADIUS_KM:
                w *= _POI_BONUS
                break
    return w * (edge.distance_m / 1000.0)


def _nearest_node(graph: RoutingGraph, lat: float, lng: float) -> int:
    best = None
    best_d = math.inf
    for nid, (nlat, nlng) in graph.nodes.items():
        d = haversine_km(lat, lng, nlat, nlng)
        if d < best_d:
            best_d, best = d, nid
    assert best is not None  # 图必须有节点
    return best


def _a_star(
    graph: RoutingGraph,
    start: int,
    target: int,
    mode: str,
    preset: str,
    pois: list[tuple[float, float]] | None,
) -> list[int] | None:
    if start == target:
        return [start]

    def h(n: int) -> float:
        nlat, nlng = graph.nodes[n]
        tlat, tlng = graph.nodes[target]
        return haversine_km(nlat, nlng, tlat, tlng) * 0.2  # 保守低估，保证可采纳

    g_cost: dict[int, float] = {start: 0.0}
    came: dict[int, int] = {}
    pq: list[tuple[float, float, int]] = [(h(start), 0.0, start)]
    visited: set[int] = set()
    while pq:
        _f, g, n = heapq.heappop(pq)
        if n in visited:
            continue
        visited.add(n)
        if n == target:
            path = [n]
            while n in came:
                n = came[n]
                path.append(n)
            return list(reversed(path))
        for e in graph.adj.get(n, []):
            cost = _edge_cost(graph, n, e, mode, preset, pois)
            if cost is None:
                continue
            ng = g + cost
            if e.target not in g_cost or ng < g_cost[e.target] - 1e-9:
                g_cost[e.target] = ng
                came[e.target] = n
                heapq.heappush(pq, (ng + h(e.target), ng, e.target))
    return None


def _edges_between(graph: RoutingGraph, frm: int, target: int) -> RouteEdge | None:
    for e in graph.adj.get(frm, []):
        if e.target == target:
            return e
    return None


def plan_route(
    graph: RoutingGraph,
    points: list[dict[str, Any]],
    mode: str = "driving",
    preset: str = "balanced",
    pois: list[tuple[float, float]] | None = None,
) -> dict[str, Any] | None:
    """按 始终/途经点 生成一条折线（GeoJSON LineString，[lng, lat]）。

    - 只取有坐标的点（无坐标点仅作标注，跳过）。
    - 相邻定位点之间 A* 最短路，按 mode×preset 边权；任一段不可达 → None。
    - 返回 {"line": …, "distance_km": …}，里程为路网真值。
    """
    located = [p for p in points if p.get("lat") is not None and p.get("lng") is not None]
    if len(located) < 2:
        return None
    coords: list[list[float]] = []
    total_m = 0.0
    for i in range(len(located) - 1):
        frm = _nearest_node(graph, located[i]["lat"], located[i]["lng"])
        target = _nearest_node(graph, located[i + 1]["lat"], located[i + 1]["lng"])
        path = _a_star(graph, frm, target, mode, preset, pois)
        if path is None:
            return None
        seg_distance = 0.0
        for j in range(len(path) - 1):
            e = _edges_between(graph, path[j], path[j + 1])
            assert e is not None
            seg_distance += e.distance_m
        total_m += seg_distance
        seg_coords = [[graph.nodes[n][1], graph.nodes[n][0]] for n in path]
        if coords and coords[-1] == seg_coords[0]:
            coords.extend(seg_coords[1:])
        else:
            coords.extend(seg_coords)
    return {
        "line": {"type": "LineString", "coordinates": coords},
        "distance_km": round(total_m / 1000.0, 1),
    }