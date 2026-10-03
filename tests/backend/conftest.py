"""共享测试夹具：临时数据根目录 + Archive + TestClient。"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from travel.main import create_app  # noqa: E402
from travel.store import Archive  # noqa: E402

from seed import build_seed  # noqa: E402


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "root"


@pytest.fixture()
def archive(data_root: Path):
    instance = Archive(data_root)
    yield instance
    instance.close()


@pytest.fixture()
def seeded_archive(data_root: Path, tmp_path: Path):
    """预置代表性旅行档案的 Archive（数据自造，见 seed.py）。"""
    instance = Archive(data_root)
    build_seed(instance, tmp_path)
    yield instance
    instance.close()


@pytest.fixture()
def greenway_graph():
    """S3+ 测试用小额路网图（公路 vs 绿道，见 test_routing.py 同构）。"""
    from travel.routing import RouteEdge, RoutingGraph

    g = RoutingGraph()
    # 0=S 1=R 2=E 3=G1 4=G2
    for nid, (lat, lng) in enumerate(
        [(30.0, 100.0), (30.0, 100.015), (30.0, 100.03), (30.0, 100.01), (30.0, 100.02)]
    ):
        g.add_node(nid, lat, lng)
    for a, b, d in [(0, 1, 1250), (1, 2, 1250), (0, 3, 3000), (3, 4, 3000), (4, 2, 3000)]:
        g.add_edge(a, RouteEdge(b, d, "tertiary" if b == 1 or a == 1 else "cycleway"))
        g.add_edge(b, RouteEdge(a, d, "tertiary" if a == 1 or b == 1 else "cycleway"))
    return g


@pytest.fixture()
def archive_with_graph(data_root: Path, greenway_graph):
    """挂载轻量路网图的 Archive（用于重算/覆盖测试）。"""
    instance = Archive(data_root, routing_graph=greenway_graph)
    yield instance
    instance.close()


@pytest.fixture()
def client_with_graph(data_root: Path, greenway_graph):
    """挂载轻量路网图的 HTTP 客户端（重算契约测试）。"""
    from fastapi.testclient import TestClient

    app = create_app(data_root, routing_graph=greenway_graph)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def client(data_root: Path):
    from fastapi.testclient import TestClient

    app = create_app(data_root)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def seeded_client(tmp_path_factory):
    """预置代表性旅行档案的 HTTP 客户端（session 级：整个进程只种一次数据）。

    种子构建含 64 条媒体逐条落库，较慢（~19s）；对只读/错误路径用例共享同一
    客户端可把契约套件整体压到 ~1 分钟。若测试需要隔离数据，请用 seeded_archive。
    """
    from fastapi.testclient import TestClient

    root = tmp_path_factory.mktemp("seed_root")
    archive = Archive(root)
    build_seed(archive, root)
    archive.close()
    app = create_app(root)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def photo_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 80, 40)).save(buf, "PNG")
    return buf.getvalue()
