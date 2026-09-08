"""SQLAlchemy 数据模型（逻辑模型见 DESIGN.md 第 4 节）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import DEFAULT_TIMEZONE


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trip"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")
    start_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    start_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    end_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    created_epoch: Mapped[float] = mapped_column(Float, default=_now_epoch)
    updated_epoch: Mapped[float] = mapped_column(Float, default=_now_epoch)


class City(Base):
    __tablename__ = "city"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class Place(Base):
    __tablename__ = "place"
    __table_args__ = (Index("ix_place_city_kind", "city_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("city.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(Text, default="scene")  # scene | shop | landmark
    name: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class Visit(Base):
    __tablename__ = "visit"
    __table_args__ = (Index("ix_visit_place", "place_id"), Index("ix_visit_trip", "trip_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("place.id", ondelete="CASCADE"))
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trip.id", ondelete="SET NULL"), nullable=True)
    at_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    at_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    at_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review: Mapped[str] = mapped_column(Text, default="")
    place_name_snapshot: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    created_epoch: Mapped[float] = mapped_column(Float, default=_now_epoch)


class TransportLeg(Base):
    __tablename__ = "transport_leg"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trip.id", ondelete="CASCADE"))
    from_text: Mapped[str] = mapped_column(Text, default="")
    to_text: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(Text, default="其他")
    depart_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    depart_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    depart_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    arrive_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    arrive_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    arrive_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Trail(Base):
    __tablename__ = "trail"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trip.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(Text, default="")
    start_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    start_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    end_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    summit_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    summit_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    summit_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    drawn_geojson: Mapped[str | None] = mapped_column(Text, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class StoredFile(Base):
    __tablename__ = "stored_file"
    __table_args__ = (Index("ix_stored_file_dedupe", "dedupe_key", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rel_path: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(Text, default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    kind: Mapped[str] = mapped_column(Text)  # photo | video
    dedupe_key: Mapped[str] = mapped_column(Text)


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        Index("ix_media_visit", "visit_id"),
        Index("ix_media_status", "status"),
        Index("ix_media_trip", "trip_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stored_file_id: Mapped[int] = mapped_column(ForeignKey("stored_file.id"))
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit.id", ondelete="SET NULL"), nullable=True)
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trip.id", ondelete="SET NULL"), nullable=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("city.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")  # attached | pending
    kind: Mapped[str] = mapped_column(Text)
    taken_at_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    taken_at_tz: Mapped[str] = mapped_column(Text, default=DEFAULT_TIMEZONE)
    taken_at_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_epoch: Mapped[float] = mapped_column(Float, default=_now_epoch)
