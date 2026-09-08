"""媒体去重、相对路径与延迟缩略图测试。"""

from __future__ import annotations

from pathlib import Path

from travel import media as media_lib
from travel.store import Archive


def test_photo_dedupe_reuses_stored_file(archive: Archive, tmp_path: Path, photo_bytes: bytes):
    src1 = tmp_path / "one.png"
    src2 = tmp_path / "two.png"
    src1.write_bytes(photo_bytes)
    src2.write_bytes(photo_bytes)

    archive.ingest_media_path(src1, "one.png")
    archive.ingest_media_path(src2, "two.png")

    rows = archive.list_media()
    assert len(rows) == 2
    stored = list((archive.root / "media").glob("*"))
    assert len(stored) == 1  # 同一内容只落盘一份


def test_video_dedupe_key_head_tail(tmp_path: Path):
    content_a = b"x" * 64 + b"HEAD" + b"y" * 64 + b"TAIL-A"
    content_b = b"x" * 64 + b"HEAD" + b"y" * 64 + b"TAIL-B"
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a_copy = tmp_path / "a_copy.mp4"
    a.write_bytes(content_a)
    b.write_bytes(content_b)
    a_copy.write_bytes(content_a)
    key_a1 = media_lib.compute_dedupe_key(a, "video")
    key_a2 = media_lib.compute_dedupe_key(a_copy, "video")
    key_b = media_lib.compute_dedupe_key(b, "video")
    assert key_a1 == key_a2
    assert key_a1 != key_b


def test_thumbnail_lazy_generation_is_idempotent(archive: Archive, tmp_path: Path, photo_bytes: bytes):
    src = tmp_path / "shot.png"
    src.write_bytes(photo_bytes)
    media = archive.ingest_media_path(src, "shot.png")
    media_id = media["id"]

    assert media["thumb"].endswith("/thumb")
    rel = archive.ensure_thumb(media_id)
    assert rel is not None and rel.startswith("thumbs/")
    thumb = archive.abs_path(rel)
    assert thumb.exists()
    mtime = thumb.stat().st_mtime

    archive.ensure_thumb(media_id)
    assert thumb.stat().st_mtime == mtime  # 已存在则不再生成


def test_media_paths_are_relative_and_inside_root(archive: Archive, tmp_path: Path, photo_bytes: bytes):
    src = tmp_path / "p.png"
    src.write_bytes(photo_bytes)
    media = archive.ingest_media_path(src, "p.png")
    rel = archive.get_media(media["id"])[1].rel_path
    assert (archive.root / rel).is_file()
    assert rel.startswith("media/")
    assert media["file"].startswith("/api/media/")
