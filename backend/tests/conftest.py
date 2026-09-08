"""共享测试夹具：临时数据根目录 + Archive + TestClient。"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from travel.main import create_app  # noqa: E402
from travel.store import Archive  # noqa: E402


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "root"


@pytest.fixture()
def archive(data_root: Path):
    instance = Archive(data_root)
    yield instance
    instance.close()


@pytest.fixture()
def client(data_root: Path):
    from fastapi.testclient import TestClient

    app = create_app(data_root)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def photo_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 80, 40)).save(buf, "PNG")
    return buf.getvalue()
