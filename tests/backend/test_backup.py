"""备份导出 / 整体恢复测试。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from travel.backup import MANIFEST
from travel.store import Archive


def test_export_restore_roundtrip(tmp_path: Path, photo_bytes: bytes):
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src = Archive(src_root)
    chengdu = src.create_city("成都", lat=30.57, lng=104.07)
    place = src.create_place("宽窄巷子", kind="scene", city_id=chengdu["id"])
    visit = src.create_visit(place["id"], at_local="2025-10-02T20:00:00", rating=4, review="人多但值得")
    media_src = tmp_path / "img.png"
    media_src.write_bytes(photo_bytes)
    src.ingest_media_path(media_src, "img.png", visit_id=visit["id"])

    export_path = tmp_path / "backup.zip"
    src.export_to(export_path)
    src.close()

    with zipfile.ZipFile(export_path) as zf:
        names = zf.namelist()
        assert "travel.db" in names and MANIFEST in names
        assert not any(n.startswith("thumbs/") for n in names)  # 缩略图不导出

    dst = Archive(dst_root)
    dst.restore_from(export_path)
    assert {c["name"] for c in dst.list_cities(lit_only=True)} == {"成都"}
    visits = dst.list_visits()
    assert visits[0]["review"] == "人多但值得"
    media = dst.list_media()
    assert len(media) == 1
    rel = dst.get_media(media[0]["id"])[1].rel_path
    assert (dst_root / rel).exists()
    dst.close()


def test_restore_rejects_foreign_zip(tmp_path: Path):
    dst_root = tmp_path / "dst"
    bogus = tmp_path / "bogus.zip"
    with zipfile.ZipFile(bogus, "w") as zf:
        zf.writestr("random.txt", "hello")
    dst = Archive(dst_root)
    try:
        dst.restore_from(bogus)
        raise AssertionError("应拒绝非备份包")
    except ValueError:
        pass
    finally:
        dst.close()
