"""共享测试种子数据：构建一份代表性旅行档案，供 contract / 前端字段比对测试复用。

覆盖点（对应测试分支）：
- 3 个到访城市 + 1 个路过城市（贵阳，无到访，验证只有 visit 点亮）。
- 每城 ≥3 地点（含地标 landmark），4 家餐馆（shop），1 条美食街。
- 跨 2024 / 2025 两年的到访，评分 / 评价 / 名称快照组合，含"再来"无行程到访。
- 媒体：微型 Pillow 真图 + 几字节占位动图（HEIC/MOV 苹果动图、单文件 JPG 安卓动态照片），
  附着（attached）与待精分（pending）两类；占位文件缩略图必然静默失败，验证 DESIGN 容错路径。
- 交通段：高铁 / 飞机 / 自驾 / 大巴。

用法：build_seed(archive, tmp_path) 返回实体 id 索引字典，供测试按需引用。
"""

from __future__ import annotations

import io
import secrets
from pathlib import Path

from PIL import Image

from travel.store import Archive

# 城市 -> (lat, lng)；贵阳为路过城市（无到访，不应点亮）
CITIES = {
    "成都": (30.57, 104.07),
    "重庆": (29.56, 106.55),
    "广州": (23.13, 113.26),
    "贵阳": (26.65, 106.63),
}

# (城市, 名称, kind, lat, lng)；含 1 条美食街
PLACES = [
    ("成都", "宽窄巷子", "scene", 30.66, 104.05),
    ("成都", "武侯祠", "scene", 30.64, 104.05),
    ("成都", "天府熊猫塔", "landmark", 30.65, 104.09),
    ("成都", "锦里美食街", "scene", 30.64, 104.05),
    ("重庆", "洪崖洞", "scene", 29.58, 106.58),
    ("重庆", "磁器口古镇", "scene", 29.60, 106.45),
    ("重庆", "朝天门", "landmark", 29.56, 106.58),
    ("广州", "陈家祠", "scene", 23.12, 113.24),
    ("广州", "沙面", "scene", 23.11, 113.24),
    ("广州", "广州塔", "landmark", 23.11, 113.32),
]
# (城市, 名称)：餐馆以 shop 类型新建，坐标留空（"无坐标"态）
RESTAURANTS = [
    ("成都", "李姐面馆"),
    ("成都", "陈麻婆豆腐店"),
    ("重庆", "磁器口毛血旺"),
    ("广州", "点都德茶楼"),
]

# 行程：(名称, note, start, end, tags)
TRIPS = [
    ("国庆成都行", "成都重庆 7 天", "2024-10-01T08:00:00", "2024-10-07T20:00:00", ["国庆", "成都"]),
    ("周末广州行", "广州两日", "2025-03-14T09:00:00", "2025-03-16T18:00:00", ["周末", "广州"]),
]

# 到访：地点名 -> [(at_local, rating, review, trip_key|None)]
VISITS = {
    "宽窄巷子": [
        ("2024-10-02T20:00:00", 4, "人多但值得", "trip1"),
        ("2025-02-15T18:30:00", 5, "夜景更好看了", None),
    ],
    "武侯祠": [("2024-10-03T09:30:00", 5, "三国迷必去", "trip1")],
    "天府熊猫塔": [("2024-10-03T19:00:00", 4, "上去看成都全景", "trip1")],
    "锦里美食街": [
        ("2024-10-04T12:00:00", 5, "一路吃过去，凉糕最好吃", "trip1"),
        ("2025-02-16T11:30:00", 3, "", None),
    ],
    "洪崖洞": [("2024-10-05T20:30:00", 5, "夜景像宫崎骏", "trip1")],
    "磁器口古镇": [
        ("2024-10-06T10:00:00", 5, "古镇很热闹", "trip1"),
        ("2025-04-05T15:00:00", None, "", None),
    ],
    "朝天门": [("2024-10-06T17:30:00", 4, "", "trip1")],
    "陈家祠": [("2025-03-15T10:00:00", 4, "岭南建筑真精致", "trip2")],
    "沙面": [("2025-03-15T15:00:00", 5, "欧陆风情街区", "trip2")],
    "广州塔": [("2025-03-16T19:30:00", 4, "登塔看夜景", "trip2")],
    "李姐面馆": [("2024-10-04T11:30:00", None, "", "trip1")],
    "陈麻婆豆腐店": [("2024-10-05T12:00:00", 4, "麻婆豆腐是招牌", "trip1")],
    "磁器口毛血旺": [("2025-04-05T18:00:00", 5, "毛血旺很香", None)],
    "点都德茶楼": [("2025-03-16T09:30:00", 5, "早茶好吃", "trip2")],
}

# 交通段：(trip_key, from, to, mode, depart, arrive, sort)
LEGS = [
    ("trip1", "北京", "成都", "高铁", "2024-10-01T08:00:00", "2024-10-01T16:30:00", 0),
    ("trip1", "成都", "重庆", "飞机", "2024-10-05T09:00:00", "2024-10-05T10:10:00", 1),
    ("trip1", "重庆", "成都", "自驾", "2024-10-06T12:00:00", "2024-10-06T17:00:00", 2),
    ("trip2", "深圳", "广州", "大巴", "2025-03-14T08:30:00", "2025-03-14T10:30:00", 0),
    ("trip2", "广州", "北京", "飞机", "2025-03-16T19:00:00", "2025-03-16T22:30:00", 1),
]

# 媒体风格列表：苹果动图用 HEIC 静帧 + MOV 视频两条；安卓动态照片用单文件 JPG。
# 真图用微缩 PNG（thumb 可生成）；占位内容几字节（thumb 必然静默失败 → 容错路径）。
_MEDIA_STYLES = [
    ("photo", "jpg", True),    # 真实照片：Pillow 生成
    ("photo", "png", True),    # 真实照片：Pillow 生成
    ("photo", "heic", False),  # 苹果 Live Photo 静帧（占位）
    ("video", "mov", False),   # 苹果 Live Photo 短视频（占位）
    ("photo", "jpg", False),   # 安卓动态照片：JPEG 内嵌视频（占位）
]


def _png_bytes(kind_idx: int) -> bytes:
    palette = [(200, 80, 40), (40, 160, 200), (120, 60, 200)]
    buf = io.BytesIO()
    Image.new("RGB", (48, 32), palette[kind_idx % len(palette)]).save(buf, "PNG")
    return buf.getvalue()


def _media_item(archive: Archive, tmp: Path, idx: int, **kw) -> dict[str, object]:
    """按风格生成一个媒体文件并导入；占位文件内容随 idx 变化保证去重键互异。"""
    kind, ext, real = _MEDIA_STYLES[idx % len(_MEDIA_STYLES)]
    if real:
        data = _png_bytes(idx)
        token = f"p{secrets.token_hex(6)}"
    else:
        data = bytes([(idx * 7 + i) % 256 for i in range(64)]) + b"#live-heic/mov/dyn"
        token = f"l{secrets.token_hex(6)}"
    filename = f"{token}.{ext}"
    src = tmp / filename
    src.write_bytes(data)
    return archive.ingest_media_path(src, filename, **kw)


def build_seed(archive: Archive, tmp: Path) -> dict[str, object]:
    """构造代表性档案并返回 id 索引。"""
    cities = {}
    for name, (lat, lng) in CITIES.items():
        cities[name] = archive.create_city(name, lat=lat, lng=lng)

    trips: dict[str, dict[str, object]] = {}
    for key, (name, note, start, end, tags) in enumerate(TRIPS, start=1):
        trips[f"trip{key}"] = archive.create_trip(name, note=note, start_local=start, end_local=end, tags=tags)

    places: dict[str, dict[str, object]] = {}
    for city, name, kind, lat, lng in PLACES:
        places[name] = archive.create_place(name, kind=kind, city_id=cities[city]["id"], lat=lat, lng=lng)
    for city, name in RESTAURANTS:
        places[name] = archive.create_place(name, kind="shop", city_id=cities[city]["id"])

    visits: list[dict[str, object]] = []
    media: list[dict[str, object]] = []
    order = 0
    for place_name, rows in VISITS.items():
        place_id = places[place_name]["id"]
        visit_ids = []
        for at_local, rating, review, trip_key in rows:
            visit = archive.create_visit(
                place_id,
                trip_id=trips[trip_key]["id"] if trip_key else None,
                at_local=at_local,
                rating=rating,
                review=review,
            )
            visits.append(visit)
            visit_ids.append(visit["id"])
        # 每地点固定条数媒体（餐馆 3、其余 5），在其各次到访间分摊，控制测试数据体积。
        count = 3 if places[place_name]["kind"] == "shop" else 5
        for i in range(count):
            at_local = rows[i % len(rows)][0]
            m = _media_item(
                archive,
                tmp,
                order,
                visit_id=visit_ids[i % len(visit_ids)],
                taken_at_local=at_local,
                gps_lat=(30.6 + order * 0.001) if i % 2 == 0 else None,
                gps_lng=(104.0 + order * 0.002) if i % 2 == 0 else None,
            )
            media.append(m)
            order += 1

    # 待精分媒体：无 visit（挂行程 / 城市级），验证 status=pending 分支
    media.append(_media_item(archive, tmp, order, trip_id=trips["trip1"]["id"], taken_at_local="2024-10-07T09:00:00"))
    media.append(_media_item(archive, tmp, order + 1, city_id=cities["成都"]["id"], taken_at_local="2025-03-17T09:00:00"))

    legs: list[dict[str, object]] = []
    for trip_key, frm, to, mode, depart, arrive, sort_order in LEGS:
        legs.append(
            archive.create_leg(
                trips[trip_key]["id"],
                from_text=frm,
                to_text=to,
                mode=mode,
                depart_local=depart,
                arrive_local=arrive,
                sort_order=sort_order,
            )
        )

    return {
        "cities": cities,
        "trips": trips,
        "places": places,
        "visits": visits,
        "media": media,
        "legs": legs,
    }