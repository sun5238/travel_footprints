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
