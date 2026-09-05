"""Index API（M10，spec §34 + DL-01 catalog/vector split）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

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
    catalog = getattr(request.app.state, "catalog_pipeline", None)
    vector_pending = catalog.pending_vector_sync() if catalog is not None else []
    return {
        "counts": counts,
        "consistent": counts["chunks"] == counts["fts_terms"] == counts["fts_trigram"],
        "last_full_scan": last_scan["value"] if last_scan else None,
        "vector_pending": len(vector_pending),
        "vector_pending_documents": [item["document_id"] for item in vector_pending[:20]],
        "inference_worker": worker,
    }


@router.post("/scan")
def index_scan(request: Request) -> dict:
    """Scan and update the model-free SQLite/FTS catalog only."""

    app = request.app
    catalog = getattr(app.state, "catalog_pipeline", None)
    if catalog is None:
        raise HTTPException(status_code=503, detail="本地全文索引服务未初始化")
    with app.state.index_lock:
        try:
            from app.indexing.scanner import scan

            result = scan(app.state.cfg, app.state.conn)
            stats = catalog.apply_scan(result)
            return {
                "scan": {
                    s: len(result.by_status(s))
                    for s in ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")
                },
                "applied": stats,
            }
        except AppError as exc:
            raise HTTPException(status_code=500, detail=f"{exc.code}: {exc}") from exc


@router.post("/reindex-document/{doc_id}")
def reindex_document(doc_id: str, request: Request) -> dict:
    """Rebuild one document's local catalog/FTS entry; vector sync stays pending."""

    app = request.app
    catalog = getattr(app.state, "catalog_pipeline", None)
    if catalog is None:
        raise HTTPException(status_code=503, detail="本地全文索引服务未初始化")
    row = app.state.conn.execute(
        "SELECT source_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    with app.state.index_lock:
        result = catalog.index_file(row["source_path"], doc_id=doc_id)
    return result


class VectorSyncBody(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/vector-sync")
def vector_sync(body: VectorSyncBody, request: Request) -> dict:
    """Explicitly synchronize pending report-derived vectors.

    This endpoint may start the inference worker or require Qdrant. Failures leave
    their durable pending marker intact.
    """

    app = request.app
    catalog = getattr(app.state, "catalog_pipeline", None)
    semantic = getattr(app.state, "pipeline", None)
    if catalog is None:
        raise HTTPException(status_code=503, detail="本地全文索引服务未初始化")
    if semantic is None:
        raise HTTPException(
            status_code=503,
            detail="Qdrant/向量索引不可用；全文检索仍可用，待服务恢复后再执行 vector-sync",
        )

    pending = catalog.pending_vector_sync()[: body.limit]
    synced = 0
    errors: list[dict] = []
    with app.state.index_lock:
        for item in pending:
            doc_id = item["document_id"]
            operation = item.get("operation", "upsert")
            source_path = item.get("source_path") or ""
            try:
                if operation == "delete":
                    semantic.remove_document(doc_id, source_path)
                else:
                    semantic.index_file(source_path, doc_id=doc_id)
                catalog.clear_vector_pending(doc_id)
                synced += 1
            except Exception as exc:
                errors.append(
                    {
                        "document_id": doc_id,
                        "operation": operation,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    remaining = len(catalog.pending_vector_sync())
    return {
        "requested": len(pending),
        "synced": synced,
        "failed": len(errors),
        "remaining": remaining,
        "errors": errors,
    }


@router.get("/cognition/status")
def cognition_index_status(request: Request) -> dict:
    """Capability/pending status for KE's read-only Cognition-derived index."""

    cog = getattr(request.app.state, "cognition", None) or {}
    if not cog.get("enabled"):
        return {
            "enabled": False,
            "lexical_available": False,
            "semantic_available": False,
            "vector_pending": 0,
            "vector_pending_documents": [],
        }
    catalog = cog.get("catalog_pipeline")
    pending = catalog.pending_vector_sync() if catalog is not None else []
    return {
        "enabled": True,
        "lexical_available": catalog is not None,
        "semantic_available": bool(cog.get("semantic_available")),
        "vector_pending": len(pending),
        "vector_pending_documents": [item["document_id"] for item in pending[:20]],
    }


@router.post("/cognition/vector-sync")
def cognition_vector_sync(body: VectorSyncBody, request: Request) -> dict:
    """Explicitly synchronize pending Cognition-derived vectors.

    The local catalog owns the stable derived ``document_id``. That id is passed
    explicitly to the semantic pipeline so a rename followed by modification
    cannot create a second path-derived vector identity. Source Cognition Markdown
    remains read-only.
    """

    app = request.app
    cog = getattr(app.state, "cognition", None) or {}
    if not cog.get("enabled"):
        raise HTTPException(status_code=404, detail="cognition 只读索引未启用")
    catalog = cog.get("catalog_pipeline")
    semantic = cog.get("semantic_pipeline")
    if catalog is None:
        raise HTTPException(status_code=503, detail="cognition 本地全文目录未初始化")
    if semantic is None or not cog.get("semantic_available", False):
        raise HTTPException(
            status_code=503,
            detail="cognition 语义索引不可用；lexical 检索仍可用，pending 状态已保留",
        )

    pending = catalog.pending_vector_sync()[: body.limit]
    synced = 0
    errors: list[dict] = []
    with app.state.index_lock:
        for item in pending:
            doc_id = item["document_id"]
            operation = item.get("operation", "upsert")
            source_path = item.get("source_path") or ""
            try:
                if operation == "delete":
                    semantic.remove_document(doc_id, source_path)
                else:
                    result = semantic.index_file(source_path, doc_id=doc_id)
                    if result.get("document_id") != doc_id:
                        raise RuntimeError(
                            f"semantic document_id mismatch: expected {doc_id}, "
                            f"got {result.get('document_id')}"
                        )
                catalog.clear_vector_pending(doc_id)
                synced += 1
            except Exception as exc:
                errors.append(
                    {
                        "document_id": doc_id,
                        "operation": operation,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    remaining = len(catalog.pending_vector_sync())
    return {
        "requested": len(pending),
        "synced": synced,
        "failed": len(errors),
        "remaining": remaining,
        "errors": errors,
    }


class RebuildBody(BaseModel):
    confirm: str  # 必须显式传 "yes"（spec §34：Rebuild 必须明确确认）


@router.post("/rebuild")
def index_rebuild(body: RebuildBody, request: Request) -> dict:
    if body.confirm != "yes":
        raise HTTPException(status_code=400, detail='rebuild 需要 {"confirm": "yes"}')
    app = request.app
    catalog = getattr(app.state, "catalog_pipeline", None)
    if catalog is None:
        raise HTTPException(status_code=503, detail="本地全文索引服务未初始化")
    with app.state.index_lock:
        try:
            from pathlib import Path

            from app.lexical.fts_search import LexicalSearcher
            from app.storage.sqlite import connect

            app.state.conn.close()
            db = Path(app.state.cfg.sqlite.path)
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(db) + suffix)
                if p.exists():
                    p.unlink()
            app.state.conn = connect(db)
            app.state.engine.conn = app.state.conn
            app.state.engine.lexical = LexicalSearcher(app.state.conn)
            app.state.catalog_pipeline.conn = app.state.conn
            if getattr(app.state, "pipeline", None) is not None:
                app.state.pipeline.conn = app.state.conn
            from app.indexing.scanner import scan

            result = scan(app.state.cfg, app.state.conn)
            stats = app.state.catalog_pipeline.apply_scan(result)
            return {
                "rebuild": "done",
                "scan": {
                    s: len(result.by_status(s))
                    for s in ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")
                },
                "applied": stats,
            }
        except AppError as exc:
            raise HTTPException(status_code=500, detail=f"{exc.code}: {exc}") from exc


@router.get("/jobs")
def index_jobs(request: Request) -> dict:
    rows = request.app.state.conn.execute(
        "SELECT * FROM indexing_jobs ORDER BY started_at DESC LIMIT 20").fetchall()
    return {"jobs": [dict(r) for r in rows]}
