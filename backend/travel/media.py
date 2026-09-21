"""媒体存储：SHA 去重、相对路径落盘、延迟缩略图（视频封面帧依赖 ffmpeg，缺失时优雅降级）。"""

from __future__ import annotations

import hashlib
import secrets
import shutil
import subprocess
from pathlib import Path

from .models import StoredFile

CHUNK = 64 * 1024

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}


def detect_kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in PHOTO_EXTS:
        return "photo"
    if ext in VIDEO_EXTS:
        return "video"
    raise ValueError(f"不支持的媒体类型: {filename}")


# EXIF GPSInfo IFD 标签号：1=纬度参照(N/S) 2=纬度 3=经度参照(E/W) 4=经度
_GPS_IFD = 0x8825
_GPS_LAT_REF, _GPS_LAT = 1, 2
_GPS_LNG_REF, _GPS_LNG = 3, 4


def _dms_to_decimal(gps_ifd: dict, ref: int, coord: int) -> float | None:
    try:
        ref_value = gps_ifd.get(ref)
        parts = gps_ifd.get(coord)
        if not parts:
            return None
        deg = float(parts[0]) if parts[0] is not None else 0.0
        minutes = float(parts[1]) if len(parts) > 1 and parts[1] is not None else 0.0
        seconds = float(parts[2]) if len(parts) > 2 and parts[2] is not None else 0.0
        value = deg + minutes / 60.0 + seconds / 3600.0
        return -value if ref_value in ("S", "W") else value
    except (TypeError, ValueError, IndexError):
        return None


def read_exif_gps(src: Path) -> tuple[float | None, float | None, float | None]:
    """读照片 EXIF GPS（Pillow，纯本地）；读不到/损坏返回 (None,None,None)，不抛错。

    坐标字段可能为 IFDRational（int/float 可直接转）或 (num, den) 形式，均先 float() 归一。
    """
    try:
        from PIL import Image

        with Image.open(src) as im:
            gps = im.getexif().get_ifd(_GPS_IFD)
            if not gps:
                return None, None, None
            lat = _dms_to_decimal(gps, _GPS_LAT_REF, _GPS_LAT)
            lng = _dms_to_decimal(gps, _GPS_LNG_REF, _GPS_LNG)
            if lat is None or lng is None:
                return None, None, None
            return lat, lng, None
    except Exception:
        return None, None, None


def photo_key(data: bytes) -> str:
    return f"p:{hashlib.sha256(data).hexdigest()}"


def video_key(head: bytes, tail: bytes) -> str:
    return f"v:{hashlib.sha256(head).hexdigest()}:{hashlib.sha256(tail).hexdigest()}"


def compute_dedupe_key(src: Path, kind: str) -> str:
    """照片全文件哈希；视频用「头尾分块」折衷，避免全量读入大文件。"""
    size = src.stat().st_size
    with src.open("rb") as fh:
        head = fh.read(CHUNK)
        if kind == "photo":
            rest = fh.read()
            return photo_key(head + rest) if rest else photo_key(head)
        if size <= CHUNK:
            return video_key(head, head)
        fh.seek(max(0, size - CHUNK))
        tail = fh.read(CHUNK)
        return video_key(head, tail)


def ingest_file(root: Path, src: Path, filename: str, existing: StoredFile | None) -> StoredFile:
    """把临时文件放入数据根目录；existing 命中去重时直接复用，不复制。"""
    if existing is not None:
        return existing
    kind = detect_kind(filename)
    ext = Path(filename).suffix.lower() or (".bin" if kind == "video" else ".jpg")
    rel = f"media/{secrets.token_hex(10)}{ext}"
    dest = root / rel
    shutil.copyfile(src, dest)
    return StoredFile(
        rel_path=rel,
        sha256=hashlib.sha256(src.read_bytes()).hexdigest() if src.stat().st_size < 50 * 1024 * 1024 else "",
        size_bytes=src.stat().st_size,
        kind=kind,
        dedupe_key=compute_dedupe_key(src, kind),
    )


def ensure_thumbnail(root: Path, stored: StoredFile) -> Path | None:
    """首次访问时生成缩略图（thumbs/{id}.jpg），失败时返回 None 而不是抛错。"""
    thumb = root / "thumbs" / f"{stored.id}.jpg"
    if thumb.exists():
        return thumb
    src = root / stored.rel_path
    if not src.exists():
        return None
    try:
        from PIL import Image

        if stored.kind == "photo":
            with Image.open(src) as im:
                im.thumbnail((360, 360))
                im.convert("RGB").save(thumb, "JPEG", quality=82)
            return thumb
        poster = _video_poster(src, root / "tmp")
        if poster is None:
            return None
        try:
            with Image.open(poster) as im:
                im.thumbnail((360, 360))
                im.convert("RGB").save(thumb, "JPEG", quality=82)
            return thumb
        finally:
            poster.unlink(missing_ok=True)
    except Exception:
        thumb.unlink(missing_ok=True)
        return None


def _video_poster(src: Path, tmp_dir: Path) -> Path | None:
    if shutil.which("ffmpeg") is None:
        return None
    poster = tmp_dir / f"poster_{secrets.token_hex(6)}.jpg"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", "-vf", "scale=360:-2", str(poster)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
    )
    return poster if result.returncode == 0 and poster.exists() else None
