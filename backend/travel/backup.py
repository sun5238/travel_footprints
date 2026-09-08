"""备份导出 / 整体恢复（zip）。

导出包含 travel.db + media/ 原文件 + manifest；缩略图不导出（懒生成，见 DESIGN.md 第 3/5.2 节）。
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_FILENAME
from .db import SCHEMA_VERSION

MANIFEST = "manifest.json"


def _media_files(root: Path) -> list[str]:
    media_dir = root / "media"
    if not media_dir.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in media_dir.iterdir() if p.is_file())


def export_archive(root: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    media = _media_files(root)
    manifest = {
        "format": "travel-footprints-backup",
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "media": media,
    }
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(root / DB_FILENAME, DB_FILENAME)
        for rel in media:
            zf.write(root / rel, rel)
        zf.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
    return dest


def restore_archive(root: Path, zip_path: Path) -> dict[str, object]:
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        if MANIFEST not in names or DB_FILENAME not in names:
            raise ValueError("不是有效的旅行足迹备份包")
        manifest = json.loads(zf.read(MANIFEST).decode("utf-8"))
        if manifest.get("format") != "travel-footprints-backup":
            raise ValueError("备份包格式不匹配")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"备份 schema 版本 {manifest.get('schema_version')} 与当前 {SCHEMA_VERSION} 不兼容"
            )
        media_names = set(manifest.get("media", []))
        if MANIFEST in media_names or DB_FILENAME in media_names:
            raise ValueError("备份包清单异常")
        _wipe(root)
        for info in zf.infolist():
            if info.is_dir() or info.filename == MANIFEST:
                continue
            target = root / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
    return {"schema_version": SCHEMA_VERSION, "media": len(media_names)}


def _wipe(root: Path) -> None:
    """整体恢复：清空 db 与 media（thumbs 属可再生的缓存，一并清理避免脏缓存）。"""
    (root / DB_FILENAME).unlink(missing_ok=True)
    for name in ("media", "thumbs"):
        shutil.rmtree(root / name, ignore_errors=True)
