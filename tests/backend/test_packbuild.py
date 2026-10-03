"""Pi: 区域路网包构建（classify_highway 纯函数 + pyrosm 惰性适配 + Archive 自动载包）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from travel.packbuild import classify_highway, pbf_to_graph
from travel.routing import RouteEdge, RoutingGraph, load_pack, save_pack
from travel.store import Archive

S = {"name": "S", "lat": 30.0, "lng": 100.0, "pos_kind": "exact"}
E = {"name": "E", "lat": 30.0, "lng": 100.03, "pos_kind": "exact"}


# ---------- highway 分类 ----------

@pytest.mark.parametrize(
    "tag,want",
    [
        ("motorway", "motorway"), ("motorway_link", "motorway"),
        ("trunk", "trunk"), ("trunk_link", "trunk"),
        ("primary", "primary"), ("primary_link", "primary"),
        ("secondary", "secondary"), ("tertiary", "tertiary"),
        ("residential", "residential"), ("unclassified", "residential"),
        ("service", "service"),
        ("cycleway", "cycleway"),
        ("path", "path"), ("track", "track"),
        ("footway", "footway"), ("pedestrian", "footway"),
        # 不参与路由
        ("steps", None), ("construction", None), ("proposed", None),
        ("busway", None), ("razed", None), ("unknown_highway", None),
    ],
)
def test_classify_highway(tag: str, want):
    assert classify_highway(tag) == want


# ---------- pyrosm 缺失时给清晰报错 ----------

def test_pbf_to_graph_without_pyrosm_raises_informative():
    import importlib.util

    if importlib.util.find_spec("pyrosm") is not None:
        pytest.skip("已装 pyrosm：缺失分支不适用（真实 PBF 集成靠用户机验证）")
    with pytest.raises(ValueError, match="pyrosm"):
        pbf_to_graph(Path("/nonexistent"))


# ---------- 区域包文件 + Archive 自动载包 ----------

def test_archive_recalc_autoloads_pack_file(data_root: Path, greenway_graph):
    """把图存为数据根 routing/pack.json，Archive 不带注入图也能重算。"""
    save_pack(greenway_graph, data_root / "routing" / "pack.json")
    archive = Archive(data_root)
    try:
        book = archive.create_routebook(
            "骑行", mode="cycling", preset="balanced", points=[S, E]
        )
        recalced = archive.recalc_routebook(book["id"])
        assert recalced["mileage_km"] == 2.5
    finally:
        archive.close()


def test_recalc_still_requires_pack_without_file(archive: Archive):
    book = archive.create_routebook("x", points=[S, E])
    with pytest.raises(ValueError, match="未配置路网"):
        archive.recalc_routebook(book["id"])


def test_build_roundtrip_matches_source_graph(data_root: Path, greenway_graph):
    """save→load 后与源图行为一致（用 greenway 档重算验证）。"""
    save_pack(greenway_graph, data_root / "routing" / "pack.json")
    loaded = load_pack(data_root / "routing" / "pack.json")
    assert loaded.nodes == greenway_graph.nodes
    assert loaded.adj[0][0].target == 1 and loaded.adj[0][0].category == "tertiary"


def test_import_packbuild_cli_help(capfd):
    from travel.packbuild import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out, _err = capfd.readouterr()
    assert "--pbf" in out and "--out" in out