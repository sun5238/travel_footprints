"""HTTP API 路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from .config import DEFAULT_TIMEZONE
from .schemas import CityIn, LegIn, PlaceIn, PlacePatch, TripIn, TripPatch, VisitIn
from .store import Archive

router = APIRouter()


def _archive(request: Request) -> Archive:
    return request.app.state.archive


def _bad(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/health")
def health() -> dict[str, object]:
    return {"ok": True}


@router.get("/dashboard")
def dashboard(request: Request) -> dict[str, object]:
    return _archive(request).dashboard()


@router.get("/trips")
def list_trips(request: Request) -> list[dict[str, object]]:
    return _archive(request).list_trips()


@router.post("/trips", status_code=201)
def create_trip(payload: TripIn, request: Request) -> dict[str, object]:
    try:
        return _archive(request).create_trip(
            payload.name,
            note=payload.note,
            start_local=payload.start_local,
            end_local=payload.end_local,
            tz=payload.tz,
            tags=payload.tags,
        )
    except ValueError as exc:
        raise _bad(exc) from exc


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, request: Request) -> dict[str, object]:
    trip = _archive(request).get_trip(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    return trip


@router.patch("/trips/{trip_id}")
def update_trip(trip_id: int, payload: TripPatch, request: Request) -> dict[str, object]:
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        return _archive(request).update_trip(trip_id, fields)
    except ValueError as exc:
        raise _bad(exc) from exc


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: int, request: Request) -> None:
    try:
        _archive(request).delete_trip(trip_id)
    except ValueError as exc:
        raise _bad(exc) from exc


@router.get("/cities")
def list_cities(request: Request, lit: bool = False) -> list[dict[str, object]]:
    return _archive(request).list_cities(lit_only=lit)


@router.post("/cities", status_code=201)
def create_city(payload: CityIn, request: Request) -> dict[str, object]:
    try:
        return _archive(request).create_city(payload.name, lat=payload.lat, lng=payload.lng, note=payload.note)
    except ValueError as exc:
        raise _bad(exc) from exc


@router.get("/cities/{city_id}")
def get_city(city_id: int, request: Request) -> dict[str, object]:
    city = _archive(request).get_city(city_id)
    if city is None:
        raise HTTPException(status_code=404, detail="城市不存在")
    return city


@router.get("/places")
def list_places(
    request: Request,
    city_id: int | None = None,
    kind: str | None = None,
    lit: bool = False,
) -> list[dict[str, object]]:
    return _archive(request).list_places(city_id=city_id, kind=kind, lit_only=lit)


@router.post("/places", status_code=201)
def create_place(payload: PlaceIn, request: Request) -> dict[str, object]:
    try:
        return _archive(request).create_place(
            payload.name,
            kind=payload.kind,
            city_id=payload.city_id,
            lat=payload.lat,
            lng=payload.lng,
            note=payload.note,
        )
    except ValueError as exc:
        raise _bad(exc) from exc


@router.patch("/places/{place_id}")
def update_place(place_id: int, payload: PlacePatch, request: Request) -> dict[str, object]:
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        return _archive(request).update_place(place_id, fields)
    except ValueError as exc:
        raise _bad(exc) from exc


@router.delete("/places/{place_id}", status_code=204)
def delete_place(place_id: int, request: Request) -> None:
    try:
        _archive(request).delete_place(place_id)
    except ValueError as exc:
        raise _bad(exc) from exc


@router.get("/places/{place_id}/visits")
def list_place_visits(place_id: int, request: Request) -> list[dict[str, object]]:
    return _archive(request).list_visits(place_id=place_id)


@router.post("/places/{place_id}/visits", status_code=201)
def create_visit(place_id: int, payload: VisitIn, request: Request) -> dict[str, object]:
    try:
        return _archive(request).create_visit(
            place_id,
            trip_id=payload.trip_id,
            at_local=payload.at_local,
            tz=payload.tz,
            rating=payload.rating,
            review=payload.review,
            tags=payload.tags,
        )
    except ValueError as exc:
        raise _bad(exc) from exc


@router.get("/visits")
def list_visits(request: Request, trip_id: int | None = None) -> list[dict[str, object]]:
    return _archive(request).list_visits(trip_id=trip_id)


@router.delete("/visits/{visit_id}", status_code=204)
def delete_visit(visit_id: int, request: Request) -> None:
    try:
        _archive(request).delete_visit(visit_id)
    except ValueError as exc:
        raise _bad(exc) from exc


@router.post("/media", status_code=201)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    visit_id: int | None = Form(None),
    trip_id: int | None = Form(None),
    city_id: int | None = Form(None),
    taken_at_local: str | None = Form(None),
    tz: str = Form(DEFAULT_TIMEZONE),
    gps_lat: float | None = Form(None),
    gps_lng: float | None = Form(None),
    gps_accuracy: float | None = Form(None),
) -> dict[str, object]:
    archive = _archive(request)
    tmp = archive.root / "tmp" / f"upload_{file.filename or 'media'}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
    await file.close()
    try:
        return archive.ingest_media_path(
            tmp,
            file.filename or "media.bin",
            visit_id=visit_id,
            trip_id=trip_id,
            city_id=city_id,
            taken_at_local=taken_at_local,
            tz=tz,
            gps_lat=gps_lat,
            gps_lng=gps_lng,
            gps_accuracy=gps_accuracy,
        )
    except ValueError as exc:
        raise _bad(exc) from exc
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/media")
def list_media(
    request: Request,
    visit_id: int | None = None,
    trip_id: int | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    return _archive(request).list_media(visit_id=visit_id, trip_id=trip_id, status=status)


@router.get("/media/{media_id}/file")
def media_file(media_id: int, request: Request) -> FileResponse:
    path = _archive(request).media_abs_path(media_id)
    return FileResponse(path)


@router.get("/media/{media_id}/thumb")
def media_thumb(media_id: int, request: Request) -> FileResponse:
    rel = _archive(request).ensure_thumb(media_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="缩略图不可用")
    return FileResponse(_archive(request).abs_path(rel), media_type="image/jpeg")


@router.delete("/media/{media_id}", status_code=204)
def delete_media(media_id: int, request: Request) -> None:
    try:
        _archive(request).delete_media(media_id)
    except ValueError as exc:
        raise _bad(exc) from exc


@router.post("/trips/{trip_id}/legs", status_code=201)
def create_leg(trip_id: int, payload: LegIn, request: Request) -> dict[str, object]:
    try:
        return _archive(request).create_leg(
            trip_id,
            from_text=payload.from_text,
            to_text=payload.to_text,
            mode=payload.mode,
            depart_local=payload.depart_local,
            arrive_local=payload.arrive_local,
            tz=payload.tz,
            note=payload.note,
            sort_order=payload.sort_order,
        )
    except ValueError as exc:
        raise _bad(exc) from exc


@router.get("/trips/{trip_id}/legs")
def list_legs(trip_id: int, request: Request) -> list[dict[str, object]]:
    return _archive(request).list_legs(trip_id)


@router.get("/backup")
def export_backup(request: Request) -> FileResponse:
    archive = _archive(request)
    dest = archive.root / "exports" / "travel-footprints-backup.zip"
    archive.export_to(dest)
    return FileResponse(dest, media_type="application/zip", filename="travel-footprints-backup.zip")


@router.post("/restore")
async def restore_backup(request: Request, file: UploadFile = File(...)) -> dict[str, object]:
    archive = _archive(request)
    tmp = Path(archive.root) / "tmp" / "restore.zip"
    with tmp.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
    await file.close()
    try:
        return archive.restore_from(tmp)
    except ValueError as exc:
        raise _bad(exc) from exc
    finally:
        tmp.unlink(missing_ok=True)
