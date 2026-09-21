"""内置城市中心坐标表（草案 §5）：**只用于点亮坐标，不参与文本识别**。

- 识别全部走 `@token`（全量必 @，见 import-draft §2.2），这张表纯粹是城市级的
  点亮坐标静态数据，无解析、无匹配、无歧义；
- CSV 随包离线打包（~几十 KB，几十个主要城市），坐标由作者/用户维护，扩到数百城
  只需追加行；`create_city` 缺坐标时自动取中心坐标补上。
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_CSV = Path(__file__).resolve().parent / "static" / "city_coords.csv"


@lru_cache(maxsize=1)
def _load() -> dict[str, tuple[float, float]]:
    table: dict[str, tuple[float, float]] = {}
    with _CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) != 3 or not row[0].strip() or row[0].startswith("#"):
                continue
            name, lat, lng = (cell.strip() for cell in row)
            try:
                table[name] = (float(lat), float(lng))
            except ValueError:
                continue
    return table


def lookup(name: str) -> tuple[float, float] | None:
    return _load().get(name)