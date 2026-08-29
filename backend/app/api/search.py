"""Search API（M10，spec §32）。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

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


@router.post("/search")
def search(body: SearchRequest, request: Request) -> dict:
    engine = request.app.state.engine
    filters = body.filters.model_dump() if body.filters else None
    if filters:
        filters = {k: v for k, v in filters.items() if v}
    try:
        return engine.search(
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
