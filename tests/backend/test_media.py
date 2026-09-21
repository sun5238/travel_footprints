"""媒体去重、相对路径、延迟缩略图与 EXIF GPS 读取测试。"""

from __future__ import annotations

import io
from fractions import Fraction
from pathlib import Path

from PIL import Image
from PIL.ExifTags import IFD

from travel import media as media_lib
from travel.store import Archive


def _jpeg_with_gps(lat: float = 30.57, lng: float = 104.07) -> bytes:
    """构造带 EXIF GPS 的 JPEG：经纬度 DMS 双向换算，浮点误差 < 1e-5。

    Pillow 写入 GPS 坐标需用 Fraction（Tiff RATIONAL），不可传 (分子, 分母) 元组。
    """
    def dms(value: float) -> tuple[int, int, float]:
        deg = int(value)
        minutes = int((value - deg) * 60)
        seconds = round((value - deg - minutes / 60) * 3600 * 1000) / 1000
        return deg, minutes, seconds

    buf = io.BytesIO()
    im = Image.new("RGB", (32, 32), (30, 60, 90))
    exif = Image.Exif()
    gps = exif.get_ifd(IFD.GPSInfo)
    gps[1] = "N" if lat >= 0 else "S"
    gps[2] = tuple(Fraction(v) for v in dms(abs(lat)))
    gps[3] = "E" if lng >= 0 else "W"
    gps[4] = tuple(Fraction(v) for v in dms(abs(lng)))
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


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


# ---------------------------------------------------------------- EXIF GPS

def test_read_exif_gps_from_jpeg(tmp_path: Path):
    src = tmp_path / "gps.jpg"
    src.write_bytes(_jpeg_with_gps(lat=30.57, lng=104.07))
    lat, lng, _acc = media_lib.read_exif_gps(src)
    assert lat is not None and lng is not None
    assert abs(lat - 30.57) < 1e-5
    assert abs(lng - 104.07) < 1e-5


def test_read_exif_gps_south_west_goes_negative(tmp_path: Path):
    src = tmp_path / "gps_sw.jpg"
    src.write_bytes(_jpeg_with_gps(lat=-33.8688, lng=-151.2093))  # 悉尼
    lat, lng, _ = media_lib.read_exif_gps(src)
    assert lat < 0 and lng < 0
    assert abs(lat + 33.8688) < 1e-4
    assert abs(lng + 151.2093) < 1e-4


def test_read_exif_gps_absent_returns_none(tmp_path: Path):
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (1, 2, 3)).save(buf, "JPEG")
    src = tmp_path / "plain.jpg"
    src.write_bytes(buf.getvalue())
    assert media_lib.read_exif_gps(src) == (None, None, None)


def test_read_exif_gps_corrupt_file_no_error(tmp_path: Path):
    src = tmp_path / "broken.jpg"
    src.write_bytes(b"not really an image")
    assert media_lib.read_exif_gps(src) == (None, None, None)


def test_ingest_autofills_gps_from_exif(archive: Archive, tmp_path: Path):
    src = tmp_path / "gps.jpg"
    src.write_bytes(_jpeg_with_gps(30.57, 104.07))
    media = archive.ingest_media_path(src, "gps.jpg")
    assert media["gps"]["lat"] is not None
    assert abs(media["gps"]["lat"] - 30.57) < 1e-5
    assert abs(media["gps"]["lng"] - 104.07) < 1e-5


def test_explicit_gps_wins_over_exif(archive: Archive, tmp_path: Path):
    src = tmp_path / "gps.jpg"
    src.write_bytes(_jpeg_with_gps(30.57, 104.07))
    media = archive.ingest_media_path(src, "gps.jpg", gps_lat=1.0, gps_lng=2.0)
    assert media["gps"]["lat"] == 1.0 and media["gps"]["lng"] == 2.0
