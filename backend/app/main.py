"""FastAPI 应用（M10，spec §32-35/44/52 + Addendum §68）。

- 仅绑定 127.0.0.1（spec §52 安全边界）；
- lifespan：启动 InferenceManager、startup reconcile、轮询 watcher 线程；
- 推理串行化由 manager 内部锁保证（spec §44 Semaphore(1) 等价）。
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import documents, evaluation, index, search, settings
from app.core.config import Config, load_config
from app.core.errors import AppError
from app.core.health import collect_health
from app.core.logging import setup_logging
from app.inference.manager import InferenceManager
from app.lexical.fts_search import LexicalSearcher
from app.retrieval.dense import DenseRetriever
from app.retrieval.rerank import RerankerService
from app.retrieval.search_engine import SearchEngine

logger = logging.getLogger(__name__)


def create_app(cfg: Config | None = None) -> FastAPI:
    if cfg is None:
        cfg = load_config()
    setup_logging(cfg.app.log_level, cfg.paths.log_dir)

    state: dict = {"watcher_stop": threading.Event(), "watcher_thread": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ---- startup ----
        from app.indexing.pipeline import EmbedderAdapter, IndexPipeline
        from app.indexing.scanner import scan
        from app.storage.migrations import init_schema
        from app.storage.sqlite import connect

        app.state.cfg = cfg
        app.state.index_lock = threading.Lock()
        app.state.conn = connect(cfg.sqlite.path, check_same_thread=False)
        init_schema(app.state.conn)

        logger.info("starting inference worker...")
        app.state.manager = InferenceManager(cfg)
        dense = DenseRetriever(cfg)
        reranker = RerankerService(cfg, app.state.manager)
        app.state.engine = SearchEngine(
            cfg, app.state.conn, dense, reranker)
        app.state.pipeline = IndexPipeline(
            cfg, app.state.conn, EmbedderAdapter(cfg, app.state.manager))
        logger.info("inference worker ready: %s (%s)", app.state.manager.device,
                    app.state.manager.device_kind)

        if cfg.indexing.startup_scan:
            def _startup_reconcile():
                with app.state.index_lock:
                    try:
                        result = scan(cfg, app.state.conn)
                        if result.has_changes:
                            stats = app.state.pipeline.apply_scan(result)
                            logger.info("startup reconcile: %s", stats)
                        else:
                            logger.info("startup reconcile: no changes")
                    except Exception:
                        logger.exception("startup reconcile 失败")

            threading.Thread(target=_startup_reconcile, daemon=True, name="startup-reconcile").start()

        # ---- 轮询 watcher（周期性全量 reconcile；spec §24 watcher 不能是唯一机制）----
        if cfg.indexing.periodic_reconcile_seconds > 0:
            def _watcher():
                interval = cfg.indexing.periodic_reconcile_seconds
                while not state["watcher_stop"].wait(interval):
                    if not app.state.index_lock.acquire(blocking=False):
                        continue
                    try:
                        result = scan(cfg, app.state.conn)
                        if result.has_changes:
                            stats = app.state.pipeline.apply_scan(result)
                            logger.info("periodic reconcile: %s", stats)
                    except Exception:
                        logger.exception("periodic reconcile 失败")
                    finally:
                        app.state.index_lock.release()

            state["watcher_thread"] = threading.Thread(
                target=_watcher, daemon=True, name="index-watcher")
            state["watcher_thread"].start()

        yield

        # ---- shutdown ----
        state["watcher_stop"].set()
        app.state.manager.shutdown()
        app.state.conn.close()
        logger.info("shutdown complete")

    app = FastAPI(title=cfg.app.name, version="0.1.0", lifespan=lifespan)
    app.include_router(search.router)
    app.include_router(documents.router)
    app.include_router(index.router)
    app.include_router(evaluation.router)
    app.include_router(settings.router)

    @app.get("/api/health")
    def health() -> dict:
        body = collect_health(cfg)
        # I0 Error/Health Model：聚合 gpu_worker 明细与 index_generation
        mgr = getattr(app.state, "manager", None)
        if mgr is not None:
            body["gpu_worker"] = {
                "alive": mgr.is_alive(), "device": mgr.device,
                "device_kind": mgr.device_kind,
                "fallback_to_cpu": mgr.fallback_to_cpu,
                "total_restarts": mgr.total_restarts,
            }
        else:
            body["gpu_worker"] = {"alive": False}
        return body

    @app.exception_handler(AppError)
    async def app_error_handler(request, exc: AppError):  # noqa: ANN001
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=getattr(exc, "http_status", 400),
            content={"error": exc.code, "message": str(exc), "detail": exc.detail},
        )

    return app


def main() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run("app.main:create_app", factory=True,
                host=cfg.app.bind_host, port=cfg.app.port, log_level="info")


if __name__ == "__main__":
    main()
