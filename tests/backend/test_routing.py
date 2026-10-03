"""M4 路由引擎纯函数（S2）：三模式×档位边权 + 禁行类别 + POI 风景折扣 + 多途经点 A*。

用手工小图断言确定性行为，不依赖真实 OSM/PBF 数据（构建工具属于后置切片）。
"""

from __future__ import annotations

import pytest

from travel.routing import RouteEdge, RoutingGraph, plan_route


# ---- 图：S-E 两可选路径（公路 vs 绿道），供骑行测试 ----

GREENWAY_S = (30.0, 100.0)
GREENWAY_E = (30.0, 100.03)
# 公路线（tertiary，2.5km）：S → R → E
# 绿道线（cycleway，9km 更长）：S → G1 → G2 → E


def _greenway_graph() -> RoutingGraph:
    g = RoutingGraph()
    # 0=S 1=R 2=E 3=G1 4=G2
    for nid, (lat, lng) in enumerate([GREENWAY_S, (30.0, 100.015), GREENWAY_E, (30.0, 100.01), (30.0, 100.02)]):
        g.add_node(nid, lat, lng)
    for a, b, d in [(0, 1, 1250), (1, 2, 1250), (0, 3, 3000), (3, 4, 3000), (4, 2, 3000)]:
        g.add_edge(a, RouteEdge(b, d, "tertiary" if b == 1 or a == 1 else "cycleway"))
        g.add_edge(b, RouteEdge(a, d, "tertiary" if a == 1 or b == 1 else "cycleway"))
    return g


# ---- 图：motorway（6km） vs secondary（8km，南绕），供自驾档位/POI 测试 ----


def _driving_graph() -> RoutingGraph:
    g = RoutingGraph()
    # 0=S 1=M1 6=E（motorway 直线 lat30）；3/4/5=secondary（南绕 lat29.95）
    coords = {
        0: (30.0, 100.0),
        1: (30.0, 100.02),
        6: (30.0, 100.04),
        3: (29.95, 100.01),
        4: (29.95, 100.02),
        5: (29.95, 100.03),
    }
    for nid, coord in coords.items():
        g.add_node(nid, *coord)
    edges = [
        (0, 1, 3000, "motorway"), (1, 6, 3000, "motorway"),
        (0, 3, 2750, "secondary"), (3, 4, 1500, "secondary"),
        (4, 5, 1500, "secondary"), (5, 6, 2250, "secondary"),
    ]
    for a, b, d, cat in edges:
        g.add_edge(a, RouteEdge(b, d, cat))
        g.add_edge(b, RouteEdge(a, d, cat))
    return g


def _pts(*coords) -> list[dict[str, float | None]]:
    return [{"name": "", "lat": lat, "lng": lng, "pos_kind": "exact"} for lat, lng in coords]


def _line_coords(result) -> list[tuple[float, float]]:
    assert result is not None
    return [(round(c[1], 5), round(c[0], 5)) for c in result["line"]["coordinates"]]


# ---------- 输出形状与几何 ----------

def test_plan_route_output_shape():
    g = _greenway_graph()
    result = plan_route(g, _pts(GREENWAY_S, GREENWAY_E), mode="cycling", preset="balanced")
    assert result is not None
    assert set(result) == {"line", "distance_km"}
    assert result["line"]["type"] == "LineString"
    assert isinstance(result["line"]["coordinates"], list)
    # GeoJSON 为 [lng, lat]
    assert all(
        isinstance(c, list) and len(c) == 2 and isinstance(c[0], float) and isinstance(c[1], float)
        for c in result["line"]["coordinates"]
    )
    assert result["distance_km"] > 0


def test_plan_route_less_than_two_located_points():
    g = _greenway_graph()
    assert plan_route(g, [{"lat": 30.0, "lng": 100.0}]) is None
    assert plan_route(g, []) is None


def test_plan_route_snaps_to_nearest_node():
    g = _greenway_graph()
    # 起点/终点略偏 → 吸附到 S/E 节点
    result = plan_route(g, _pts((30.0002, 100.0003), (30.0002, 100.0302)), mode="cycling", preset="balanced")
    assert _line_coords(result)[0] == GREENWAY_S
    assert _line_coords(result)[-1] == GREENWAY_E


# ---------- 模式×档位偏好 ----------

def test_cycling_balanced_prefers_shorter_road():
    g = _greenway_graph()
    result = plan_route(g, _pts(GREENWAY_S, GREENWAY_E), mode="cycling", preset="balanced")
    assert _line_coords(result) == [GREENWAY_S, (30.0, 100.015), GREENWAY_E]
    assert result["distance_km"] == 2.5


def test_cycling_greenway_prefers_greenway_even_if_longer():
    g = _greenway_graph()
    result = plan_route(g, _pts(GREENWAY_S, GREENWAY_E), mode="cycling", preset="greenway")
    assert result is not None
    # 绿道线 S→G1→G2→E，虽 9km 长于公路 2.5km，仍被选中
    assert _line_coords(result) == [
        GREENWAY_S, (30.0, 100.01), (30.0, 100.02), GREENWAY_E,
    ]


@pytest.mark.parametrize("preset", ["balanced", "fast"])
def test_driving_prefers_motorway_without_poi(preset):
    g = _driving_graph()
    result = plan_route(g, _pts((30.0, 100.0), (30.0, 100.04)), mode="driving", preset=preset)
    assert _line_coords(result) == [(30.0, 100.0), (30.0, 100.02), (30.0, 100.04)]
    assert result["distance_km"] == 6.0


def test_driving_scenic_without_poi_still_prefers_motorway():
    g = _driving_graph()
    result = plan_route(g, _pts((30.0, 100.0), (30.0, 100.04)), mode="driving", preset="scenic")
    assert _line_coords(result) == [(30.0, 100.0), (30.0, 100.02), (30.0, 100.04)]


def test_driving_scenic_with_poi_prefers_scenic_secondary():
    g = _driving_graph()
    # 景点在 secondary 中段（远离 motorway 直线走廊）
    result = plan_route(
        g,
        _pts((30.0, 100.0), (30.0, 100.04)),
        mode="driving",
        preset="scenic",
        pois=[(29.95, 100.02)],
    )
    assert _line_coords(result) == [
        (30.0, 100.0), (29.95, 100.01), (29.95, 100.02), (29.95, 100.03), (30.0, 100.04),
    ]
    assert result["distance_km"] == 8.0


# ---------- 禁行类别 ----------

def test_walking_and_cycling_refuse_motorway_only_corridor():
    g = RoutingGraph()
    g.add_node(0, 30.0, 100.0)
    g.add_node(1, 30.0, 100.02)
    g.add_edge(0, RouteEdge(1, 2200, "motorway"))
    g.add_edge(1, RouteEdge(0, 2200, "motorway"))
    assert plan_route(g, _pts((30.0, 100.0), (30.0, 100.02)), mode="walking") is None
    assert plan_route(g, _pts((30.0, 100.0), (30.0, 100.02)), mode="cycling") is None


def test_walking_uses_footway_when_available():
    g = RoutingGraph()
    g.add_node(0, 30.0, 100.0)
    g.add_node(1, 30.0, 100.02)
    g.add_node(2, 30.0, 100.01)
    # motorway 直连仍禁行，但 footway 绕行可达
    g.add_edge(0, RouteEdge(1, 2200, "motorway"))
    g.add_edge(1, RouteEdge(0, 2200, "motorway"))
    g.add_edge(0, RouteEdge(2, 1400, "footway"))
    g.add_edge(2, RouteEdge(1, 1400, "footway"))
    g.add_edge(2, RouteEdge(0, 1400, "footway"))
    g.add_edge(1, RouteEdge(2, 1400, "footway"))
    result = plan_route(g, _pts((30.0, 100.0), (30.0, 100.02)), mode="walking")
    assert _line_coords(result) == [(30.0, 100.0), (30.0, 100.01), (30.0, 100.02)]


# ---------- 多途经点 ----------

def test_multi_point_route_passes_through_via():
    g = RoutingGraph()
    # 链：S(0)→A(1)→V(2)→B(3)→E(4)，外加 S→C(5)→E 捷径（2.6km，但必经 V 则不走捷径）
    for nid, (lat, lng) in enumerate(
        [(30.0, 100.0), (30.0, 100.01), (30.0, 100.02), (30.0, 100.03), (30.0, 100.04), (30.0, 100.02)]
    ):
        g.add_node(nid, lat, lng)
    for a, b, d in [(0, 1, 1200), (1, 2, 1200), (2, 3, 1200), (3, 4, 1200), (0, 5, 1300), (5, 4, 1300)]:
        g.add_edge(a, RouteEdge(b, d, "tertiary"))
        g.add_edge(b, RouteEdge(a, d, "tertiary"))
    result = plan_route(
        g,
        _pts((30.0, 100.0), (30.0, 100.02), (30.0, 100.04)),
        mode="driving",
        preset="balanced",
    )
    assert result is not None
    # 途经点 (30,100.02) 在线上；全程链 4×1.2km，绕开 2.6km 捷径
    assert (30.0, 100.02) in _line_coords(result)
    assert result["distance_km"] == 4.8


def test_coords_less_via_point_is_skipped():
    g = _greenway_graph()
    # 中间带一个无坐标点（仅标注），路由跳过它 S→E 直达
    pts = [
        {"name": "", "lat": 30.0, "lng": 100.0, "pos_kind": "exact"},
        {"name": "", "lat": None, "lng": None, "pos_kind": "none"},
        {"name": "", "lat": 30.0, "lng": 100.03, "pos_kind": "exact"},
    ]
    result = plan_route(g, pts, mode="cycling", preset="balanced")
    assert _line_coords(result) == [GREENWAY_S, (30.0, 100.015), GREENWAY_E]