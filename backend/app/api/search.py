"""Search API（M10，spec §32）+ Personal Retrieval Feedback。"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, model_validator

from app.retrieval.feedback import (
    FEEDBACK_SCHEMA_VERSION,
    append_feedback_events,
    build_impression_events,
    feedback_path,
)

router = APIRouter(prefix="/api", tags=["search"])
logger = logging.getLogger(__name__)


class SearchFilters(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    evidence_levels: list[int] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None


class SearchOptions(BaseModel):
    # Base Research OS path is deterministic/local. Semantic retrieval is explicit.
    mode: str = "lexical"  # hybrid | dense | lexical
    rerank: bool = False
    top_k: int = Field(default=10, ge=1, le=50)
    debug: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    filters: SearchFilters | None = None
    options: SearchOptions = Field(default_factory=SearchOptions)


FeedbackEventType = Literal[
    "impression",
    "useful",
    "evidence_select",
    "evidence_remove",
]
FeedbackMode = Literal["lexical", "dense", "hybrid"]


class RetrievalFeedbackEvent(BaseModel):
    """One local feedback observation tied to a concrete displayed result."""

    search_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=500)
    chunk_id: str = Field(min_length=1, max_length=300)
    document_id: str | None = Field(default=None, max_length=200)
    rank: int = Field(ge=1, le=50)
    mode: FeedbackMode
    rerank: bool = False
    event_type: FeedbackEventType
    useful: bool | None = None
    selected_as_evidence: bool | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "RetrievalFeedbackEvent":
        if self.event_type == "useful" and self.useful is None:
            raise ValueError("useful event requires useful=true/false")
        if self.event_type in {"evidence_select", "evidence_remove"} and self.selected_as_evidence is None:
            raise ValueError("evidence action requires selected_as_evidence")
        return self


class RetrievalFeedbackBatch(BaseModel):
    events: list[RetrievalFeedbackEvent] = Field(min_length=1, max_length=50)


def _record_impressions(request: Request, body: SearchRequest, response: dict) -> None:
    """Best-effort logging: telemetry failure must never make retrieval fail."""

    search_id = uuid4().hex
    mode = str(response.get("mode") or body.options.mode)
    results = response.get("results") or []

    for result in results:
        if isinstance(result, dict):
            result["search_id"] = search_id
            result["search_mode"] = mode
            result["rerank_enabled"] = body.options.rerank
    response["search_id"] = search_id

    try:
        events = build_impression_events(
            search_id=search_id,
            query=body.query,
            mode=mode,
            rerank=body.options.rerank,
            results=[item for item in results if isinstance(item, dict)],
        )
        append_feedback_events(
            feedback_path(request.app.state.cfg.paths.data_dir),
            events,
        )
    except Exception:
        logger.exception("retrieval feedback impression 写入失败；忽略并继续返回搜索结果")


@router.post("/search")
def search(body: SearchRequest, request: Request) -> dict:
    if body.options.mode in ("hybrid", "dense") and not getattr(request.app.state, "qdrant_available", True):
        from fastapi import HTTPException

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
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _record_impressions(request, body, response)
    return response


@router.post("/retrieval-feedback")
def retrieval_feedback(body: RetrievalFeedbackBatch, request: Request) -> dict:
    """Append explicit local usefulness / Evidence-selection feedback.

    This endpoint only records observations. It never changes retrieval weights,
    reranker behavior, Evidence membership, TaskPacks, or Cognition state.
    """

    recorded = append_feedback_events(
        feedback_path(request.app.state.cfg.paths.data_dir),
        [event.model_dump() for event in body.events],
    )
    return {"recorded": recorded, "schema_version": FEEDBACK_SCHEMA_VERSION}


@router.post("/search/cognition")
def cognition_search(body: SearchRequest, request: Request) -> dict:
    """I6：Cognition 只读语义检索（独立 collection，结果带 scope 来源标识）。

    READ ONLY：KE 对 cognition 只读消费，本端点无任何写路径。
    """
    cog = getattr(request.app.state, "cognition", None)
    if cog is None or not cog.get("enabled"):
        from fastapi import HTTPException

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
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
    resp["scope"] = "cognition"
    return resp
