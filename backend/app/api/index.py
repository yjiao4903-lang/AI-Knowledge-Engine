"""Index API（M10，spec §34）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.errors import AppError

router = APIRouter(prefix="/api/index", tags=["index"])


@router.get("/status")
def index_status(request: Request) -> dict:
    conn = request.app.state.conn
    cfg = request.app.state.cfg
    counts = {
        "documents": conn.execute("SELECT count(*) FROM documents").fetchone()[0],
        "sections": conn.execute("SELECT count(*) FROM sections").fetchone()[0],
        "chunks": conn.execute("SELECT count(*) FROM chunks").fetchone()[0],
        "fts_terms": conn.execute("SELECT count(*) FROM chunks_fts_terms").fetchone()[0],
        "fts_trigram": conn.execute("SELECT count(*) FROM chunks_fts_trigram").fetchone()[0],
    }
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=cfg.qdrant.url, timeout=10)
        counts["qdrant_points"] = client.count(
            collection_name=cfg.qdrant.chunks_collection, exact=True).count
    except Exception as exc:
        counts["qdrant_error"] = str(exc)
    last_scan = conn.execute(
        "SELECT value FROM meta WHERE key = 'last_full_scan'").fetchone()
    worker = request.app.state.manager.health() if request.app.state.manager else {"alive": False}
    return {"counts": counts, "consistent":
            counts["chunks"] == counts["fts_terms"] == counts["fts_trigram"],
            "last_full_scan": last_scan["value"] if last_scan else None,
            "inference_worker": worker}


@router.post("/scan")
def index_scan(request: Request) -> dict:
    """全量 manifest 扫描并应用变更（同步返回；全量语料耗时与规模成正比）。"""
    app = request.app
    if getattr(app.state, "pipeline", None) is None:
        raise HTTPException(status_code=503, detail="Qdrant 不可用，索引服务暂不可用")
    with app.state.index_lock:
        try:
            from app.indexing.scanner import scan

            result = scan(app.state.cfg, app.state.conn)
            stats = app.state.pipeline.apply_scan(result)
            return {"scan": {s: len(result.by_status(s)) for s in
                             ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")},
                    "applied": stats}
        except AppError as exc:
            raise HTTPException(status_code=500, detail=f"{exc.code}: {exc}") from exc


@router.post("/reindex-document/{doc_id}")
def reindex_document(doc_id: str, request: Request) -> dict:
    app = request.app
    if getattr(app.state, "pipeline", None) is None:
        raise HTTPException(status_code=503, detail="Qdrant 不可用，索引服务暂不可用")
    row = app.state.conn.execute(
        "SELECT source_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    with app.state.index_lock:
        result = app.state.pipeline.index_file(row["source_path"])
    return result


class RebuildBody(BaseModel):
    confirm: str  # 必须显式传 "yes"（spec §34：Rebuild 必须明确确认）


@router.post("/rebuild")
def index_rebuild(body: RebuildBody, request: Request) -> dict:
    if body.confirm != "yes":
        raise HTTPException(status_code=400, detail='rebuild 需要 {"confirm": "yes"}')
    app = request.app
    if getattr(app.state, "pipeline", None) is None:
        raise HTTPException(status_code=503, detail="Qdrant 不可用，索引服务暂不可用")
    with app.state.index_lock:
        try:
            from app.storage.sqlite import connect

            app.state.conn.close()
            from pathlib import Path

            db = Path(app.state.cfg.sqlite.path)
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(db) + suffix)
                if p.exists():
                    p.unlink()
            app.state.conn = connect(db)
            app.state.engine.conn = app.state.conn
            app.state.pipeline.conn = app.state.conn
            from app.indexing.scanner import scan

            result = scan(app.state.cfg, app.state.conn)
            stats = app.state.pipeline.apply_scan(result)
            return {"rebuild": "done", "scan": {s: len(result.by_status(s)) for s in
                                                ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")},
                    "applied": stats}
        except AppError as exc:
            raise HTTPException(status_code=500, detail=f"{exc.code}: {exc}") from exc


@router.get("/jobs")
def index_jobs(request: Request) -> dict:
    rows = request.app.state.conn.execute(
        "SELECT * FROM indexing_jobs ORDER BY started_at DESC LIMIT 20").fetchall()
    return {"jobs": [dict(r) for r in rows]}
