"""Pi: 路由图序列化/打包（to_pack/from_pack + save_pack/load_pack 文件往返）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from travel.routing import RouteEdge, RoutingGraph, load_pack, save_pack


def _small_graph() -> RoutingGraph:
    g = RoutingGraph()
    g.add_node(1, 30.0, 100.0)
    g.add_node(2, 30.0, 100.01)
    g.add_node(3, 30.0, 100.02)
    g.add_edge(1, RouteEdge(2, 1100.5, "tertiary"))
    g.add_edge(2, RouteEdge(1, 1100.5, "tertiary"))
    g.add_edge(2, RouteEdge(3, 900.0, "cycleway"))
    g.add_edge(3, RouteEdge(2, 900.0, "cycleway"))
    return g


def test_pack_roundtrip():
    g = _small_graph()
    h = RoutingGraph.from_pack(g.to_pack())
    assert h.nodes == g.nodes
    # adj 按 dict 列表比较（顺序即插入序，roundtrip 保持）
    assert {n: [(e.target, e.distance_m, e.category) for e in es] for n, es in h.adj.items()} == {
        n: [(e.target, e.distance_m, e.category) for e in es] for n, es in g.adj.items()
    }


def test_save_load_pack_file_roundtrip(tmp_path: Path):
    g = _small_graph()
    dest = tmp_path / "pack.json"
    save_pack(g, dest)
    assert dest.exists()
    loaded = load_pack(dest)
    assert loaded.nodes == g.nodes
    assert len(loaded.adj[2]) == 2


def test_load_pack_rejects_bogus(tmp_path: Path):
    dest = tmp_path / "pack.json"
    dest.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pack(dest)


def test_pack_compact_values():
    """打包格式是紧凑数组，避免区域级体积爆炸。"""
    g = _small_graph()
    pack = g.to_pack()
    assert "nodes" in pack and "edges" in pack
    assert all(isinstance(n, list) and len(n) == 3 for n in pack["nodes"])
    assert all(len(e) == 4 for e in pack["edges"])
    assert pack["nodes"][0] == [1, 30.0, 100.0]