"""Settings API（M10）：返回脱敏后的运行配置与检索参数。"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_settings(request: Request) -> dict:
    cfg = request.app.state.cfg
    return {
        "app": cfg.app.model_dump(),
        "knowledge_base": cfg.knowledge_base.model_dump(),
        "retrieval": cfg.retrieval.model_dump(),
        "fusion": cfg.fusion.model_dump(),
        "chunking": cfg.chunking.model_dump(),
        "embedding": {"model": cfg.embedding.model, "dimension": cfg.embedding.dimension,
                      "query_instruction": cfg.embedding.query_instruction},
        "reranker": cfg.reranker.model_dump(),
        "inference": cfg.inference.model_dump(),
    }
