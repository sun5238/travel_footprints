"""FastAPI 应用工厂与入口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import resolve_data_root
from .store import Archive

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app(data_root: str | Path | None = None) -> FastAPI:
    archive = Archive(data_root)
    app = FastAPI(title="Travel Footprints", version="0.1.0")
    app.state.archive = archive
    app.include_router(router, prefix="/api")

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


app = create_app()


def run(host: str = "127.0.0.1", port: int = 8000, data_root: str | None = None) -> None:
    import uvicorn

    global app
    app = create_app(data_root)
    uvicorn.run(app, host=host, port=port)
