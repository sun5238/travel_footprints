"""领域仓储：数据根目录内所有读写操作的唯一入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine

from . import media as media_lib
from . import backup
from .config import DEFAULT_TIMEZONE, ensure_layout, resolve_data_root
from .db import connect
from .models import City, Media, Place, StoredFile, Trail, TransportLeg, Trip, Visit
from .timeutil import to_epoch, to_local_iso


def _parse_tags(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def _dump_tags(tags: list[str] | None) -> str:
    return json.dumps(tags or [], ensure_ascii=False)


class Archive:
    """一个数据根目录 = 一个 Archive 实例；所有路径相对，绝对路径只在本类内从数据根推导。"""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.root = resolve_data_root(data_root)
        ensure_layout(self.root)
        self._engine, self._factory = connect(self.root)

    def close(self) -> None:
        self._engine.dispose()

    def _session(self) -> Session:
        return self._factory()

    def _reconnect(self) -> None:
        self._engine.dispose()
        ensure_layout(self.root)
        self._engine, self._factory = connect(self.root)

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
    ) -> dict[str, Any]:
        if rating is not None and not 1 <= rating <= 5:
            raise ValueError("评分需在 1-5 之间")
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
            stats = {
                "cities_lit": lit_city_count,
                "cities": int(s.scalar(select(func.count(City.id))) or 0),
                "places": int(s.scalar(select(func.count(Place.id))) or 0),
                "visits": int(s.scalar(select(func.count(Visit.id))) or 0),
                "media": int(s.scalar(select(func.count(Media.id))) or 0),
                "media_pending": int(
                    s.scalar(select(func.count(Media.id)).where(Media.status == "pending")) or 0
                ),
                "trails": int(s.scalar(select(func.count(Trail.id))) or 0),
                "distance_km": float(
                    s.scalar(select(func.coalesce(func.sum(Trail.distance_m), 0) / 1000.0)) or 0.0
                ),
            }
            trips = [
                _trip_dict(t)
                for t in s.scalars(
                    select(Trip).order_by(Trip.start_epoch.desc().nulls_last(), Trip.id.desc()).limit(10)
                ).all()
            ]
        return {"stats": stats, "lit_cities": self.list_cities(lit_only=True), "recent_trips": trips}

    # ---------- 交通段 / 轨迹（M3 使用，先落表） ----------

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
        )
        with self._session() as s:
            s.add(leg)
            s.commit()
            return _leg_dict(leg)

    def list_legs(self, trip_id: int) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.scalars(select(TransportLeg).where(TransportLeg.trip_id == trip_id).order_by(TransportLeg.sort_order)).all()
            return [_leg_dict(leg) for leg in rows]

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
    }
