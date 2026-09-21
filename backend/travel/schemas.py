"""HTTP 请求体校验。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .config import DEFAULT_TIMEZONE


class TripIn(BaseModel):
    name: str
    note: str = ""
    start_local: str | None = None
    end_local: str | None = None
    tz: str = DEFAULT_TIMEZONE
    tags: list[str] = []


class TripPatch(BaseModel):
    name: str | None = None
    note: str | None = None
    start_local: str | None = None
    end_local: str | None = None
    tags: list[str] | None = None


class CityIn(BaseModel):
    name: str
    lat: float | None = None
    lng: float | None = None
    note: str = ""


class PlaceIn(BaseModel):
    name: str
    kind: Literal["scene", "shop", "landmark"] = "scene"
    city_id: int | None = None
    lat: float | None = None
    lng: float | None = None
    note: str = ""


class PlacePatch(BaseModel):
    name: str | None = None
    kind: Literal["scene", "shop", "landmark"] | None = None
    city_id: int | None = None
    lat: float | None = None
    lng: float | None = None
    note: str | None = None


class VisitIn(BaseModel):
    trip_id: int | None = None
    at_local: str | None = None
    tz: str = DEFAULT_TIMEZONE
    rating: int | None = Field(default=None, ge=1, le=5)
    review: str = ""
    tags: list[str] = []
    # M2（import-draft §7）：主活动标签 / 同行人 / 坐标来源 / 轨迹增强
    label: str | None = None
    companions: list[str] = []
    pos_kind: Literal["none", "point", "entry"] = "none"
    gpx_path: str | None = None
    drawn_geojson: str | None = None
    difficulty: str | None = None


class VisitPatch(BaseModel):
    trip_id: int | None = None
    at_local: str | None = None
    tz: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    review: str | None = None
    tags: list[str] | None = None
    label: str | None = None
    companions: list[str] | None = None
    pos_kind: Literal["none", "point", "entry"] | None = None
    gpx_path: str | None = None
    drawn_geojson: str | None = None
    difficulty: str | None = None


class LegIn(BaseModel):
    from_text: str = ""
    to_text: str = ""
    mode: str = "其他"
    depart_local: str | None = None
    arrive_local: str | None = None
    tz: str = DEFAULT_TIMEZONE
    note: str = ""
    sort_order: int = 0
    price: float | None = None


class LegPatch(BaseModel):
    from_text: str | None = None
    to_text: str | None = None
    mode: str | None = None
    depart_local: str | None = None
    arrive_local: str | None = None
    tz: str | None = None
    note: str | None = None
    sort_order: int | None = None
    price: float | None = None


class MediaBatchIn(BaseModel):
    ids: list[int]
    action: Literal["unassign", "delete"]


class ParseIn(BaseModel):
    text: str
    tz: str = DEFAULT_TIMEZONE
