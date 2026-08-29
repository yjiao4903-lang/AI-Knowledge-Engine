"""Documents / Chunks API（M10，spec §33）。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents")
def list_documents(request: Request) -> dict:
    conn = request.app.state.conn
    rows = conn.execute(
        "SELECT id, report_code, title, domain, status, completed_at, source_path, "
        "file_name, indexed_at FROM documents ORDER BY id").fetchall()
    return {"documents": [dict(r) for r in rows], "total": len(rows)}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    doc = dict(row)
    doc["chunk_count"] = conn.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ?", (doc_id,)).fetchone()[0]
    doc["section_count"] = conn.execute(
        "SELECT count(*) FROM sections WHERE document_id = ?", (doc_id,)).fetchone()[0]
    return doc


@router.get("/documents/{doc_id}/sections")
def get_document_sections(doc_id: str, request: Request) -> dict:
    conn = request.app.state.conn
    rows = conn.execute(
        "SELECT id, parent_section_id, level, heading, heading_path, section_type, "
        "ordinal, start_line, end_line FROM sections WHERE document_id = ? ORDER BY ordinal",
        (doc_id,)).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    return {"document_id": doc_id, "sections": [dict(r) for r in rows]}


@router.get("/documents/{doc_id}/chunks")
def get_document_chunks(doc_id: str, request: Request) -> dict:
    """按文档列出全部 chunks（I0 契约端点，主计划 §18）。

    替代前端依赖 chunk_id 确定性的探针枚举方案；仅元数据 + 正文，不含向量。
    """
    conn = request.app.state.conn
    if conn.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    rows = conn.execute(
        "SELECT id, document_id, section_id, ordinal, content_type, evidence_level, "
        "start_line, end_line, plain_text FROM chunks WHERE document_id = ? ORDER BY ordinal",
        (doc_id,)).fetchall()
    total = len(rows)
    return {"document_id": doc_id, "chunks": [dict(r) for r in rows],
            "total": total, "chunk_count": total}


@router.get("/chunks/{chunk_id}")
def get_chunk(chunk_id: str, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT c.*, d.title FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
        "WHERE c.id = ?", (chunk_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"chunk not found: {chunk_id}")
    return dict(row)


def _validate_in_roots(source_path: str, allowed_roots: list[str]) -> Path:
    """Path Traversal 防护（spec §52）：resolved 必须位于允许根内。"""
    resolved = Path(source_path).resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(Path(root).resolve())
            return resolved
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail=f"path outside allowed roots: {resolved}")


@router.post("/documents/{doc_id}/open-original")
def open_original(doc_id: str, request: Request) -> dict:
    conn = request.app.state.conn
    cfg = request.app.state.cfg
    row = conn.execute("SELECT source_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    resolved = _validate_in_roots(row["source_path"], cfg.knowledge_base.roots)
    if not resolved.exists():
        raise HTTPException(status_code=410, detail=f"file missing: {resolved}")
    os.startfile(str(resolved))  # noqa: S606 - 本地单用户系统，路径已过白名单校验
    return {"opened": True, "path": str(resolved)}
