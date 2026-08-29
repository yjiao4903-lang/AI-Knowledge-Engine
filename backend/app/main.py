"""FastAPI 应用骨架（M1-07）。

M1 仅提供 /api/health；search/documents/index 等 API 在后续 Milestone 接入。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.core.config import Config, load_config
from app.core.errors import AppError
from app.core.health import collect_health
from app.core.logging import setup_logging


def create_app(cfg: Config | None = None) -> FastAPI:
    if cfg is None:
        cfg = load_config()
    setup_logging(cfg.app.log_level, cfg.paths.log_dir)

    app = FastAPI(title=cfg.app.name, version="0.1.0")
    app.state.config = cfg

    @app.get("/api/health")
    def health() -> dict:
        return collect_health(cfg)

    @app.exception_handler(AppError)
    async def app_error_handler(request, exc: AppError):  # noqa: ANN001
        return _json_error(exc.code, str(exc), exc.detail)

    return app


def _json_error(code: str, message: str, detail: dict) -> "JSONResponse":  # type: ignore[name-defined]
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content={"error": code, "message": message, "detail": detail})
