"""Search API（M10，spec §32）+ Personal Retrieval Feedback。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.retrieval.feedback import record_search_results, update_feedback

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["search"])


class SearchFilters(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    evidence_levels: list[int] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None


class SearchOptions(BaseModel):
    mode: str = "hybrid"  # hybrid | dense | lexical
    rerank: bool = True
    top_k: int = Field(default=10, ge=1, le=50)
    debug: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    filters: SearchFilters | None = None
    options: SearchOptions = Field(default_factory=SearchOptions)


class RetrievalFeedbackUpdate(BaseModel):
    """Update explicit user feedback for one result exposure from a prior search."""

    search_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=500)
    useful: bool | None = None
    selected_as_evidence: bool | None = None

    @model_validator(mode="after")
    def require_signal(self):
        if self.useful is None and self.selected_as_evidence is None:
            raise ValueError("useful / selected_as_evidence 至少提供一个")
        return self


def _capture_search_feedback(request: Request, response: dict, fallback_query: str, fallback_mode: str) -> None:
    """Best-effort exposure capture; feedback storage must never break retrieval."""

    try:
        response["search_id"] = record_search_results(
            request.app.state.conn,
            query=str(response.get("query") or fallback_query),
            mode=str(response.get("mode") or fallback_mode),
            results=list(response.get("results") or []),
        )
    except Exception:  # pragma: no cover - defensive degraded path
        logger.exception("retrieval feedback exposure capture failed")
        response["search_id"] = None


@router.post("/search")
def search(body: SearchRequest, request: Request) -> dict:
    if body.options.mode in ("hybrid", "dense") and not getattr(request.app.state, "qdrant_available", True):
        raise HTTPException(status_code=503, detail="Qdrant 不可用，dense/hybrid 检索暂不可用；可改用 lexical 模式")
    engine = request.app.state.engine
    filters = body.filters.model_dump() if body.filters else None
    if filters:
        filters = {k: v for k, v in filters.items() if v}
    try:
        response = engine.search(
            body.query,
            mode=body.options.mode,
            top_k=body.options.top_k,
            filters=filters,
            debug=body.options.debug,
            rerank=body.options.rerank,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _capture_search_feedback(request, response, body.query, body.options.mode)
    return response


@router.post("/retrieval-feedback")
def retrieval_feedback(body: RetrievalFeedbackUpdate, request: Request) -> dict:
    """Record explicit useful / Evidence-selection feedback for one search result."""

    row = update_feedback(
        request.app.state.conn,
        search_id=body.search_id,
        chunk_id=body.chunk_id,
        useful=body.useful,
        selected_as_evidence=body.selected_as_evidence,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="retrieval feedback exposure not found")
    return row


@router.post("/search/cognition")
def cognition_search(body: SearchRequest, request: Request) -> dict:
    """I6：Cognition 只读语义检索（独立 collection，结果带 scope 来源标识）。

    READ ONLY：KE 对 cognition 只读消费，本端点无任何写路径。
    Personal Retrieval Feedback 当前只记录 report Search，不混入 Cognition scope。
    """
    cog = getattr(request.app.state, "cognition", None)
    if cog is None or not cog.get("enabled"):
        raise HTTPException(status_code=404, detail="cognition 语义检索未启用")
    engine = cog["engine"]
    filters = body.filters.model_dump() if body.filters else None
    if filters:
        filters = {k: v for k, v in filters.items() if v}
    try:
        resp = engine.search(
            body.query,
            mode=body.options.mode,
            top_k=body.options.top_k,
            filters=filters,
            debug=body.options.debug,
            rerank=body.options.rerank,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    resp["scope"] = "cognition"
    return resp
