"""领域仓储：数据根目录内所有读写操作的唯一入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine

from . import backup
from . import city_coords as city_coords_table
from . import media as media_lib
from .gpx import routebook_to_gpx
from .nav import nav_links
from .routing import RoutingGraph, load_pack, plan_route
from .routebook_pack import read_routebook_zip, write_routebook_zip
from .config import DEFAULT_TIMEZONE, ensure_layout, resolve_data_root
from .db import connect
from .models import (
    City,
    Media,
    Place,
    RouteBook,
    RoutePoint,
    RouteStop,
    StoredFile,
    TransportLeg,
    Trip,
    Visit,
    _now_epoch,
)

_MODES = ("driving", "cycling", "walking")
_POS_KINDS = ("none", "city", "exact")
_STOP_TYPES = ("charging", "fuel", "scene", "lodging")
from .timeutil import to_epoch, to_local_iso


def _parse_list(raw: str) -> list[str]:
    """JSON 数组文本 -> list；损坏/非数组返回空（标签与同行人共用）。"""
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def _dump_list(values: list[str] | None) -> str:
    return json.dumps(values or [], ensure_ascii=False)


def _parse_tags(raw: str) -> list[str]:
    return _parse_list(raw)


def _dump_tags(tags: list[str] | None) -> str:
    return _dump_list(tags)


def _norm_route_points(points: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    for i, p in enumerate(points or []):
        pos_kind = (p.get("pos_kind") or "none").lower()
        stop_type = p.get("stop_type")
        if pos_kind not in _POS_KINDS:
            raise ValueError(f"未知坐标来源: {pos_kind}")
        if stop_type is not None and stop_type not in _STOP_TYPES:
            raise ValueError(f"未知停靠类型: {stop_type}")
    return [
        {
            "seq": i,
            "name": (p.get("name") or ""),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "pos_kind": (p.get("pos_kind") or "none").lower(),
            "stop_type": p.get("stop_type"),
            "stop_name": (p.get("stop_name") or ""),
            "stop_note": (p.get("stop_note") or ""),
        }
        for i, p in enumerate(points or [])
    ]


def _norm_route_stops(stops: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    for i, st in enumerate(stops or []):
        pos_kind = (st.get("pos_kind") or "none").lower()
        stop_type = (st.get("stop_type") or "scene").lower()
        if pos_kind not in _POS_KINDS:
            raise ValueError(f"未知坐标来源: {pos_kind}")
        if stop_type not in _STOP_TYPES:
            raise ValueError(f"未知停靠类型: {stop_type}")
    return [
        {
            "seq": i,
            "name": (st.get("name") or ""),
            "lat": st.get("lat"),
            "lng": st.get("lng"),
            "pos_kind": (st.get("pos_kind") or "none").lower(),
            "stop_type": (st.get("stop_type") or "scene").lower(),
            "stop_note": (st.get("stop_note") or ""),
        }
        for i, st in enumerate(stops or [])
    ]


def _fetch_route_points(s: Session, routebook_id: int) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(RoutePoint).where(RoutePoint.routebook_id == routebook_id).order_by(RoutePoint.seq)
    ).all()
    return [_point_dict(p) for p in rows]


def _fetch_route_stops(s: Session, routebook_id: int) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(RouteStop).where(RouteStop.routebook_id == routebook_id).order_by(RouteStop.seq)
    ).all()
    return [_stop_dict(st) for st in rows]


def _replace_route_points(s: Session, routebook_id: int, points: list[dict[str, Any]]) -> None:
    s.execute(delete(RoutePoint).where(RoutePoint.routebook_id == routebook_id))
    for p in points:
        s.add(RoutePoint(routebook_id=routebook_id, **p))


def _replace_route_stops(s: Session, routebook_id: int, stops: list[dict[str, Any]]) -> None:
    s.execute(delete(RouteStop).where(RouteStop.routebook_id == routebook_id))
    for st in stops:
        s.add(RouteStop(routebook_id=routebook_id, **st))


class Archive:
    """一个数据根目录 = 一个 Archive 实例；所有路径相对，绝对路径只在本类内从数据根推导。"""

    def __init__(
        self,
        data_root: str | Path | None = None,
        routing_graph: RoutingGraph | None = None,
    ) -> None:
        self.root = resolve_data_root(data_root)
        ensure_layout(self.root)
        self._engine, self._factory = connect(self.root)
        # M4 路书：轻量路由图（真实图来自区域路网包构建工具，ADR-0008）
        self._routing_graph = routing_graph

    def close(self) -> None:
        self._engine.dispose()

    def _session(self) -> Session:
        return self._factory()

    def _reconnect(self) -> None:
        self._engine.dispose()
        ensure_layout(self.root)
        self._engine, self._factory = connect(self.root)

    def _load_routing_pack(self) -> RoutingGraph | None:
        """数据根 routing/pack.json 存在则载入路由图（惰性，仅首次 recalc 触发）。"""
        pack_path = self.root / "routing" / "pack.json"
        if not pack_path.exists():
            return None
        try:
            return load_pack(pack_path)
        except ValueError:
            return None

    def abs_path(self, rel: str) -> Path:
        return self.root / rel

    # ---------- Trips ----------

    def create_trip(
        self,
        name: str,
        note: str = "",
        start_local: str | None = None,
        end_local: str | None = None,
        tz: str = DEFAULT_TIMEZONE,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        trip = Trip(
            name=name,
            note=note,
            start_local=to_local_iso(start_local, tz),
            start_tz=tz,
            start_epoch=to_epoch(start_local, tz),
            end_local=to_local_iso(end_local, tz),
            end_tz=tz,
            end_epoch=to_epoch(end_local, tz),
            tags=_dump_tags(tags),
        )
        with self._session() as s:
            s.add(trip)
            s.commit()
            return _trip_dict(trip)

    def list_trips(self) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.scalars(select(Trip).order_by(Trip.start_epoch.desc(), Trip.id.desc())).all()
            return [_trip_dict(t) for t in rows]

    def get_trip(self, trip_id: int) -> dict[str, Any] | None:
        with self._session() as s:
            trip = s.get(Trip, trip_id)
            return _trip_dict(trip) if trip else None

    def update_trip(self, trip_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {"name", "note", "start_local", "end_local", "tags"}
        with self._session() as s:
            trip = s.get(Trip, trip_id)
            if trip is None:
                raise ValueError(f"行程不存在: {trip_id}")
            for key, value in fields.items():
                if key not in allowed:
                    continue
                if key == "tags":
                    setattr(trip, "tags", _dump_tags(value))
                elif key in ("start_local", "end_local"):
                    col = "start" if key == "start_local" else "end"
                    tz = getattr(trip, f"{col}_tz")
                    setattr(trip, key, to_local_iso(value, tz))
                    setattr(trip, f"{col}_epoch", to_epoch(value, tz))
                else:
                    setattr(trip, key, value)
            s.commit()
            return _trip_dict(trip)

    def delete_trip(self, trip_id: int) -> None:
        with self._session() as s:
            trip = s.get(Trip, trip_id)
            if trip is None:
                raise ValueError(f"行程不存在: {trip_id}")
            s.execute(update(Media).where(Media.trip_id == trip_id).values(trip_id=None))
            s.delete(trip)
            s.commit()

    # ---------- Cities ----------

    def create_city(
        self, name: str, lat: float | None = None, lng: float | None = None, note: str = ""
    ) -> dict[str, Any]:
        # 城市级点亮兜底（草案 §5）：未显式给坐标时取内置中心坐标表，仅点亮用、不参与识别
        if lat is None and lng is None:
            center = city_coords_table.lookup(name)
            if center is not None:
                lat, lng = center
        with self._session() as s:
            if s.scalar(select(City).where(City.name == name)) is not None:
                raise ValueError(f"城市已存在: {name}")
            city = City(name=name, lat=lat, lng=lng, note=note)
            s.add(city)
            s.commit()
            return _city_dict(city)

    def list_cities(self, lit_only: bool = False) -> list[dict[str, Any]]:
        q = (
            select(City, func.count(func.distinct(Visit.id)), func.count(func.distinct(Place.id)))
            .outerjoin(Place, Place.city_id == City.id)
            .outerjoin(Visit, Visit.place_id == Place.id)
            .group_by(City.id)
            .order_by(City.name)
        )
        if lit_only:
            q = q.having(func.count(func.distinct(Visit.id)) > 0)
        with self._session() as s:
            rows = s.execute(q).all()
            return [
                _city_dict(city, visit_count=int(visit_count or 0), place_count=int(place_count or 0))
                for city, visit_count, place_count in rows
            ]

    def get_city(self, city_id: int) -> dict[str, Any] | None:
        with self._session() as s:
            city = s.get(City, city_id)
            return _city_dict(city) if city else None

    # ---------- Places ----------

    def create_place(
        self,
        name: str,
        kind: str = "scene",
        city_id: int | None = None,
        lat: float | None = None,
        lng: float | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        if kind not in ("scene", "shop", "landmark"):
            raise ValueError(f"未知地点类型: {kind}")
        with self._session() as s:
            place = Place(name=name, kind=kind, city_id=city_id, lat=lat, lng=lng, note=note)
            s.add(place)
            s.commit()
            return _place_dict(place)

    def list_places(
        self,
        city_id: int | None = None,
        kind: str | None = None,
        lit_only: bool = False,
    ) -> list[dict[str, Any]]:
        q = (
            select(Place, func.count(func.distinct(Visit.id)))
            .outerjoin(Visit, Visit.place_id == Place.id)
            .group_by(Place.id)
            .order_by(Place.name)
        )
        if city_id is not None:
            q = q.where(Place.city_id == city_id)
        if kind is not None:
            q = q.where(Place.kind == kind)
        if lit_only:
            q = q.having(func.count(func.distinct(Visit.id)) > 0)
        with self._session() as s:
            rows = s.execute(q).all()
            return [_place_dict(place, visit_count=int(visit_count or 0)) for place, visit_count in rows]

    def update_place(self, place_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {"name", "kind", "city_id", "lat", "lng", "note"}
        with self._session() as s:
            place = s.get(Place, place_id)
            if place is None:
                raise ValueError(f"地点不存在: {place_id}")
            for key, value in fields.items():
                if key in allowed:
                    setattr(place, key, value)
            s.commit()
            return _place_dict(place)

    def delete_place(self, place_id: int) -> None:
        with self._session() as s:
            place = s.get(Place, place_id)
            if place is None:
                raise ValueError(f"地点不存在: {place_id}")
            s.delete(place)
            s.flush()
            s.execute(
                update(Media)
                .where(Media.visit_id.is_(None), Media.status == "attached")
                .values(status="pending")
            )
            s.commit()

    # ---------- Visits ----------

    def create_visit(
        self,
        place_id: int,
        trip_id: int | None = None,
        at_local: str | None = None,
        tz: str = DEFAULT_TIMEZONE,
        rating: int | None = None,
        review: str = "",
        tags: list[str] | None = None,
        label: str | None = None,
        companions: list[str] | None = None,
        pos_kind: str = "none",
        gpx_path: str | None = None,
        drawn_geojson: str | None = None,
        difficulty: str | None = None,
    ) -> dict[str, Any]:
        if rating is not None and not 1 <= rating <= 5:
            raise ValueError("评分需在 1-5 之间")
        if pos_kind not in ("none", "point", "entry"):
            raise ValueError(f"未知坐标来源: {pos_kind}")
        with self._session() as s:
            place = s.get(Place, place_id)
            if place is None:
                raise ValueError(f"地点不存在: {place_id}")
            visit = Visit(
                place_id=place_id,
                trip_id=trip_id,
                at_local=to_local_iso(at_local, tz),
                at_tz=tz,
                at_epoch=to_epoch(at_local, tz),
                rating=rating,
                review=review,
                place_name_snapshot=place.name,
                tags=_dump_tags(tags),
                label=label,
                companions=_dump_list(companions),
                pos_kind=pos_kind,
                gpx_path=gpx_path,
                drawn_geojson=drawn_geojson,
                difficulty=difficulty,
            )
            s.add(visit)
            s.commit()
            return _visit_dict(visit)

    def list_visits(self, place_id: int | None = None, trip_id: int | None = None) -> list[dict[str, Any]]:
        q = select(Visit).order_by(Visit.at_epoch.desc().nulls_last(), Visit.id.desc())
        if place_id is not None:
            q = q.where(Visit.place_id == place_id)
        if trip_id is not None:
            q = q.where(Visit.trip_id == trip_id)
        with self._session() as s:
            rows = s.scalars(q).all()
            return [_visit_dict(v) for v in rows]

    def delete_visit(self, visit_id: int) -> None:
        with self._session() as s:
            visit = s.get(Visit, visit_id)
            if visit is None:
                raise ValueError(f"到访记录不存在: {visit_id}")
            s.execute(update(Media).where(Media.visit_id == visit_id).values(status="pending"))
            s.delete(visit)
            s.commit()

    def update_visit(self, visit_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        """仅更新非 None 字段（Schema Patch 语义，见 TripPatch 先例）；at_local+tz 重算 epoch。"""
        allowed = {
            "at_local", "tz", "rating", "review", "tags", "label",
            "companions", "pos_kind", "gpx_path", "drawn_geojson", "difficulty",
        }
        with self._session() as s:
            visit = s.get(Visit, visit_id)
            if visit is None:
                raise ValueError(f"到访记录不存在: {visit_id}")
            for key, value in fields.items():
                if key not in allowed or value is None:
                    continue
                if key in ("tags", "companions"):
                    setattr(visit, key, _dump_list(value))
                elif key == "at_local":
                    tz = fields.get("tz") or visit.at_tz
                    visit.at_local = to_local_iso(value, tz)
                    visit.at_tz = tz
                    visit.at_epoch = to_epoch(value, tz)
                elif key == "tz":
                    visit.at_tz = value
                    visit.at_epoch = to_epoch(visit.at_local, value)
                elif key == "rating" and not 1 <= value <= 5:
                    raise ValueError("评分需在 1-5 之间")
                elif key == "pos_kind" and value not in ("none", "point", "entry"):
                    raise ValueError(f"未知坐标来源: {value}")
                else:
                    setattr(visit, key, value)
            s.commit()
            return _visit_dict(visit)

    # ---------- Media ----------

    def ingest_media_path(
        self,
        src: Path,
        filename: str,
        visit_id: int | None = None,
        trip_id: int | None = None,
        city_id: int | None = None,
        taken_at_local: str | None = None,
        tz: str = DEFAULT_TIMEZONE,
        gps_lat: float | None = None,
        gps_lng: float | None = None,
        gps_accuracy: float | None = None,
    ) -> dict[str, Any]:
        kind = media_lib.detect_kind(filename)
        key = media_lib.compute_dedupe_key(src, kind)
        # 坐标三级兜底第一级（草案 §3）：照片自带 EXIF GPS 则自动取坐标；读不到/已显式传入则不覆盖
        if kind == "photo" and gps_lat is None and gps_lng is None:
            exif_lat, exif_lng, _acc = media_lib.read_exif_gps(src)
            if exif_lat is not None:
                gps_lat, gps_lng = exif_lat, exif_lng
        with self._session() as s:
            existing = s.scalar(select(StoredFile).where(StoredFile.dedupe_key == key))
            stored = media_lib.ingest_file(self.root, src, filename, existing)
            if existing is None:
                s.add(stored)
                s.flush()
            item = Media(
                stored_file_id=stored.id,
                visit_id=visit_id,
                trip_id=trip_id,
                city_id=city_id,
                status="attached" if visit_id is not None else "pending",
                kind=kind,
                taken_at_local=to_local_iso(taken_at_local, tz),
                taken_at_tz=tz,
                taken_at_epoch=to_epoch(taken_at_local, tz),
                gps_lat=gps_lat,
                gps_lng=gps_lng,
                gps_accuracy=gps_accuracy,
            )
            s.add(item)
            s.commit()
            return _media_dict(item, stored)

    def list_media(
        self, visit_id: int | None = None, trip_id: int | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        q = select(Media, StoredFile).join(StoredFile, Media.stored_file_id == StoredFile.id)
        if visit_id is not None:
            q = q.where(Media.visit_id == visit_id)
        if trip_id is not None:
            q = q.where(Media.trip_id == trip_id)
        if status is not None:
            q = q.where(Media.status == status)
        q = q.order_by(Media.taken_at_epoch.desc().nulls_last(), Media.id.desc())
        with self._session() as s:
            rows = s.execute(q).all()
            return [_media_dict(item, stored) for item, stored in rows]

    def get_media(self, media_id: int) -> tuple[Media, StoredFile] | None:
        with self._session() as s:
            q = (
                select(Media, StoredFile)
                .join(StoredFile, Media.stored_file_id == StoredFile.id)
                .where(Media.id == media_id)
            )
            row = s.execute(q).first()
            return (row[0], row[1]) if row else None

    def delete_media(self, media_id: int) -> None:
        with self._session() as s:
            item = s.get(Media, media_id)
            if item is None:
                raise ValueError(f"媒体不存在: {media_id}")
            s.delete(item)
            s.commit()

    def batch_media(self, media_ids: list[int], action: str) -> dict[str, int]:
        """批量操作媒体（草案 §8.2）：unassign=解绑回 pending（不删文件）；delete=删行。单事务。"""
        if action not in ("unassign", "delete"):
            raise ValueError(f"未知批量操作: {action}")
        if not media_ids:
            raise ValueError("未指定媒体")
        with self._session() as s:
            rows = s.scalars(select(Media).where(Media.id.in_(media_ids))).all()
            if len(rows) != len(set(media_ids)):
                raise ValueError("存在不存在的媒体 id")
            if action == "unassign":
                for item in rows:
                    item.visit_id = None
                    item.status = "pending"
            else:
                for item in rows:
                    s.delete(item)
            s.commit()
        return {"updated": len(rows)}

    def ensure_thumb(self, media_id: int) -> str | None:
        pair = self.get_media(media_id)
        if pair is None:
            raise ValueError(f"媒体不存在: {media_id}")
        item, stored = pair
        thumb = media_lib.ensure_thumbnail(self.root, stored)
        return None if thumb is None else f"thumbs/{stored.id}.jpg"

    def media_abs_path(self, media_id: int) -> Path:
        pair = self.get_media(media_id)
        if pair is None:
            raise ValueError(f"媒体不存在: {media_id}")
        _item, stored = pair
        return self.abs_path(stored.rel_path)

    # ---------- Dashboard ----------

    def dashboard(self) -> dict[str, Any]:
        with self._session() as s:
            lit_city_count = int(
                s.scalar(
                    select(func.count(func.distinct(City.id)))
                    .select_from(City)
                    .join(Place, Place.city_id == City.id)
                    .join(Visit, Visit.place_id == Place.id)
                )
                or 0
            )
            label_rows = s.execute(
                select(Visit.label, func.count())
                .where(Visit.label.isnot(None))
                .group_by(Visit.label)
                .order_by(func.count().desc())
            ).all()
            stats = {
                "cities_lit": lit_city_count,
                "cities": int(s.scalar(select(func.count(City.id))) or 0),
                "places": int(s.scalar(select(func.count(Place.id))) or 0),
                "visits": int(s.scalar(select(func.count(Visit.id))) or 0),
                "media": int(s.scalar(select(func.count(Media.id))) or 0),
                "media_pending": int(
                    s.scalar(select(func.count(Media.id)).where(Media.status == "pending")) or 0
                ),
                # M2：轨迹并入 visit，按主活动标签聚合（爬山 X 次…）；M2 不设轨迹/里程卡
                "label_stats": [{"label": label, "count": int(count)} for label, count in label_rows],
            }
            trips = [
                _trip_dict(t)
                for t in s.scalars(
                    select(Trip).order_by(Trip.start_epoch.desc().nulls_last(), Trip.id.desc()).limit(10)
                ).all()
            ]
        return {"stats": stats, "lit_cities": self.list_cities(lit_only=True), "recent_trips": trips}

    # ---------- 交通段（M2 用之；轨迹已并入 visit，见 import-draft §7） ----------

    def create_leg(
        self,
        trip_id: int,
        from_text: str = "",
        to_text: str = "",
        mode: str = "其他",
        depart_local: str | None = None,
        arrive_local: str | None = None,
        tz: str = DEFAULT_TIMEZONE,
        note: str = "",
        sort_order: int = 0,
        price: float | None = None,
    ) -> dict[str, Any]:
        leg = TransportLeg(
            trip_id=trip_id,
            from_text=from_text,
            to_text=to_text,
            mode=mode,
            depart_local=to_local_iso(depart_local, tz),
            depart_tz=tz,
            depart_epoch=to_epoch(depart_local, tz),
            arrive_local=to_local_iso(arrive_local, tz),
            arrive_tz=tz,
            arrive_epoch=to_epoch(arrive_local, tz),
            note=note,
            sort_order=sort_order,
            price=price,
        )
        with self._session() as s:
            s.add(leg)
            s.commit()
            return _leg_dict(leg)

    def list_legs(self, trip_id: int) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.scalars(select(TransportLeg).where(TransportLeg.trip_id == trip_id).order_by(TransportLeg.sort_order)).all()
            return [_leg_dict(leg) for leg in rows]

    def update_leg(self, leg_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        """仅更新非 None 字段；出发/到达时刻 + tz 重算 epoch。"""
        allowed = {
            "from_text", "to_text", "mode", "depart_local", "arrive_local",
            "tz", "note", "sort_order", "price",
        }
        with self._session() as s:
            leg = s.get(TransportLeg, leg_id)
            if leg is None:
                raise ValueError(f"交通段不存在: {leg_id}")
            for key, value in fields.items():
                if key not in allowed or value is None:
                    continue
                if key in ("depart_local", "arrive_local"):
                    col = "depart" if key == "depart_local" else "arrive"
                    tz = fields.get("tz") or getattr(leg, f"{col}_tz")
                    setattr(leg, key, to_local_iso(value, tz))
                    setattr(leg, f"{col}_tz", tz)
                    setattr(leg, f"{col}_epoch", to_epoch(value, tz))
                elif key == "tz":
                    leg.depart_tz = value
                    leg.arrive_tz = value
                    leg.depart_epoch = to_epoch(leg.depart_local, value)
                    leg.arrive_epoch = to_epoch(leg.arrive_local, value)
                else:
                    setattr(leg, key, value)
            s.commit()
            return _leg_dict(leg)

    # ---------- 路书（M4，独立模块；ADR-0008） ----------

    def create_routebook(
        self,
        name: str,
        mode: str = "driving",
        preset: str = "balanced",
        points: list[dict[str, Any]] | None = None,
        stops: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if mode not in _MODES:
            raise ValueError(f"未知模式: {mode}")
        norm_points = _norm_route_points(points)
        norm_stops = _norm_route_stops(stops)
        with self._session() as s:
            book = RouteBook(name=name, mode=mode, preset=preset)
            s.add(book)
            s.flush()
            for p in norm_points:
                s.add(RoutePoint(routebook_id=book.id, **p))
            for st in norm_stops:
                s.add(RouteStop(routebook_id=book.id, **st))
            s.commit()
            # 返回落库后的真实行（含 DB 分配的 id），与 get_routebook 形状一致
            points = _fetch_route_points(s, book.id)
            stops = _fetch_route_stops(s, book.id)
            return _routebook_dict(book, points, stops)

    def recalc_routebook(self, routebook_id: int) -> dict[str, Any]:
        """按当前途经点/模式/档位重算引擎线（S3）。

        - 无路网图 → 报错（需安装区域路网包）。
        - 段不可达 / 有坐标点不足 2 个 → 报错，不落库。
        - 引擎线落 geometry_source=engine；若为用户覆盖线则不重算（S4 语义）。
        - 手动里程（mileage_manual）不被重算吞掉。
        """
        with self._session() as s:
            book = s.get(RouteBook, routebook_id)
            if book is None:
                raise ValueError(f"路书不存在: {routebook_id}")
            points = _fetch_route_points(s, routebook_id)
            stops = _fetch_route_stops(s, routebook_id)
            if book.geometry_source == "override":
                raise ValueError("当前为手绘覆盖线，重算不会覆盖；如需引擎线请先清除覆盖")
        if self._routing_graph is None:
            self._routing_graph = self._load_routing_pack()
            if self._routing_graph is None:
                raise ValueError("未配置路网图（请先建区域路网包并放入数据根 routing/pack.json，见 scripts/build-routing-pack.sh）")
        pois = [
            (st["lat"], st["lng"]) for st in stops if st["lat"] is not None and st["lng"] is not None
        ]
        planned = plan_route(
            self._routing_graph,
            points,
            mode=book.mode,
            preset=book.preset,
            pois=pois or None,
        )
        if planned is None:
            raise ValueError("无法生成路线：坐标不足或段不可达，请补充/调整途经点")
        with self._session() as s:
            book = s.get(RouteBook, routebook_id)
            assert book is not None  # 上面已验存在
            book.geometry_source = "engine"
            book.geometry_json = json.dumps(planned["line"], ensure_ascii=False)
            if not book.mileage_manual:
                book.mileage_km = planned["distance_km"]
            book.updated_epoch = _now_epoch()
            s.commit()
            points = _fetch_route_points(s, routebook_id)
            stops = _fetch_route_stops(s, routebook_id)
            return _routebook_dict(book, points, stops)

    def list_routebooks(self) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.scalars(
                select(RouteBook).order_by(RouteBook.updated_epoch.desc(), RouteBook.id.desc())
            ).all()
            return [_routebook_header(b) for b in rows]

    def get_routebook(self, routebook_id: int) -> dict[str, Any] | None:
        with self._session() as s:
            book = s.get(RouteBook, routebook_id)
            if book is None:
                return None
            points = _fetch_route_points(s, routebook_id)
            stops = _fetch_route_stops(s, routebook_id)
            return _routebook_dict(book, points, stops)

    def update_routebook(self, routebook_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "name", "mode", "preset", "mileage_km", "mileage_manual",
            "geometry_source", "geometry_json",
        }
        with self._session() as s:
            book = s.get(RouteBook, routebook_id)
            if book is None:
                raise ValueError(f"路书不存在: {routebook_id}")
            if "mode" in fields and fields["mode"] is not None:
                if fields["mode"] not in _MODES:
                    raise ValueError(f"未知模式: {fields['mode']}")
            if "geometry_source" in fields and fields["geometry_source"] is not None:
                if fields["geometry_source"] not in ("engine", "override"):
                    raise ValueError(f"未知几何来源: {fields['geometry_source']}")
            for key, value in fields.items():
                if key in allowed and value is not None:
                    setattr(book, key, value)
            if "mileage_km" in fields and "mileage_manual" not in fields:
                # 显式给出里程即视为手动值（真值重算时不吞掉，见 S4）；
                # 导入还原时可显式带 mileage_manual，精确复原
                book.mileage_manual = fields["mileage_km"] is not None
            if "points" in fields and fields["points"] is not None:
                _replace_route_points(s, routebook_id, _norm_route_points(fields["points"]))
            if "stops" in fields and fields["stops"] is not None:
                _replace_route_stops(s, routebook_id, _norm_route_stops(fields["stops"]))
            book.updated_epoch = _now_epoch()
            s.commit()
            points = _fetch_route_points(s, routebook_id)
            stops = _fetch_route_stops(s, routebook_id)
            return _routebook_dict(book, points, stops)

    def export_routebook_gpx(self, routebook_id: int) -> str:
        """路书 → GPX 1.1 `<rte>` 文本（S5/S6，供浏览器下载）。"""
        book = self.get_routebook(routebook_id)
        if book is None:
            raise ValueError(f"路书不存在: {routebook_id}")
        return routebook_to_gpx(book["name"], book["points"])

    def routebook_nav(self, routebook_id: int) -> dict[str, Any]:
        """路书导航交接三件套（S7：腾讯/高德深链 + 文本兜底）。"""
        book = self.get_routebook(routebook_id)
        if book is None:
            raise ValueError(f"路书不存在: {routebook_id}")
        return nav_links(book["name"], book["mode"], book["points"])

    def export_routebook(self, routebook_id: int) -> Path:
        """把路书打成自包含 zip（exports/routebook-<id>.zip）。"""
        book = self.get_routebook(routebook_id)
        if book is None:
            raise ValueError(f"路书不存在: {routebook_id}")
        dest = self.root / "exports" / f"routebook-{routebook_id}.zip"
        return write_routebook_zip(book, dest)

    def import_routebook(self, zip_path: Path) -> dict[str, Any]:
        """导入路书包 → 新建一本（同名不覆盖），还原几何/里程精确态。"""
        data = read_routebook_zip(zip_path)
        book = self.create_routebook(
            data["name"],
            mode=data["mode"],
            preset=data["preset"],
            points=data["points"],
            stops=data["stops"],
        )
        fields: dict[str, Any] = {}
        if data.get("geometry_json"):
            fields["geometry_json"] = data["geometry_json"]
            fields["geometry_source"] = data["geometry_source"]
        if data.get("mileage_km") is not None:
            fields["mileage_km"] = data["mileage_km"]
            fields["mileage_manual"] = data["mileage_manual"]
        if fields:
            return self.update_routebook(book["id"], fields)
        return book

    def delete_routebook(self, routebook_id: int) -> None:
        with self._session() as s:
            book = s.get(RouteBook, routebook_id)
            if book is None:
                raise ValueError(f"路书不存在: {routebook_id}")
            s.delete(book)  # 途经点/停靠由 FK ON DELETE CASCADE 级联清理
            s.commit()

    # ---------- 备份 ----------

    def export_to(self, dest: Path) -> Path:
        return backup.export_archive(self.root, dest)

    def restore_from(self, zip_path: Path) -> dict[str, object]:
        self._engine.dispose()
        result = backup.restore_archive(self.root, zip_path)
        self._reconnect()
        return result


def _trip_dict(t: Trip) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "note": t.note,
        "start": {"local": t.start_local, "tz": t.start_tz, "epoch": t.start_epoch},
        "end": {"local": t.end_local, "tz": t.end_tz, "epoch": t.end_epoch},
        "tags": _parse_tags(t.tags),
        "created_epoch": t.created_epoch,
        "updated_epoch": t.updated_epoch,
    }


def _parse_geojson(raw: str | None) -> Any | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _routebook_header(b: RouteBook) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "mode": b.mode,
        "preset": b.preset,
        "mileage_km": b.mileage_km,
        "mileage_manual": b.mileage_manual,
        "geometry": {"source": b.geometry_source, "geojson": _parse_geojson(b.geometry_json)},
        "created_epoch": b.created_epoch,
        "updated_epoch": b.updated_epoch,
    }


def _routebook_dict(
    book: RouteBook, points: list[dict[str, Any]], stops: list[dict[str, Any]]
) -> dict[str, Any]:
    return {**_routebook_header(book), "points": points, "stops": stops}


def _point_dict(p: RoutePoint) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "lat": p.lat,
        "lng": p.lng,
        "pos_kind": p.pos_kind,
        "stop_type": p.stop_type,
        "stop_name": p.stop_name,
        "stop_note": p.stop_note,
    }


def _stop_dict(st: RouteStop) -> dict[str, Any]:
    return {
        "id": st.id,
        "name": st.name,
        "lat": st.lat,
        "lng": st.lng,
        "pos_kind": st.pos_kind,
        "stop_type": st.stop_type,
        "stop_note": st.stop_note,
    }


def _city_dict(c: City, visit_count: int = 0, place_count: int = 0) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "lat": c.lat,
        "lng": c.lng,
        "note": c.note,
        "lit": visit_count > 0,
        "visit_count": visit_count,
        "place_count": place_count,
    }


def _place_dict(p: Place, visit_count: int = 0) -> dict[str, Any]:
    return {
        "id": p.id,
        "city_id": p.city_id,
        "kind": p.kind,
        "name": p.name,
        "lat": p.lat,
        "lng": p.lng,
        "note": p.note,
        "lit": visit_count > 0,
        "visit_count": visit_count,
    }


def _visit_dict(v: Visit) -> dict[str, Any]:
    return {
        "id": v.id,
        "place_id": v.place_id,
        "trip_id": v.trip_id,
        "at": {"local": v.at_local, "tz": v.at_tz, "epoch": v.at_epoch},
        "rating": v.rating,
        "review": v.review,
        "place_name_snapshot": v.place_name_snapshot,
        "tags": _parse_tags(v.tags),
        "label": v.label,
        "companions": _parse_list(v.companions),
        "pos_kind": v.pos_kind,
        "gpx_path": v.gpx_path,
        "drawn_geojson": v.drawn_geojson,
        "difficulty": v.difficulty,
        "created_epoch": v.created_epoch,
    }


def _media_dict(m: Media, stored: StoredFile) -> dict[str, Any]:
    return {
        "id": m.id,
        "kind": m.kind,
        "status": m.status,
        "visit_id": m.visit_id,
        "trip_id": m.trip_id,
        "city_id": m.city_id,
        "taken_at": {"local": m.taken_at_local, "tz": m.taken_at_tz, "epoch": m.taken_at_epoch},
        "gps": {"lat": m.gps_lat, "lng": m.gps_lng, "accuracy": m.gps_accuracy},
        "size_bytes": stored.size_bytes,
        "file": f"/api/media/{m.id}/file",
        "thumb": f"/api/media/{m.id}/thumb",
    }


def _leg_dict(leg: TransportLeg) -> dict[str, Any]:
    return {
        "id": leg.id,
        "trip_id": leg.trip_id,
        "from": leg.from_text,
        "to": leg.to_text,
        "mode": leg.mode,
        "depart": {"local": leg.depart_local, "epoch": leg.depart_epoch},
        "arrive": {"local": leg.arrive_local, "epoch": leg.arrive_epoch},
        "note": leg.note,
        "sort_order": leg.sort_order,
        "price": leg.price,
    }
