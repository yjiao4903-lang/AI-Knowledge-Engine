"""L1 Synthesis API（主计划 §14/§15）。

L1A 严格只做三件事：read evidence → generate draft → return draft。
禁止（§15）：/api/agent、/api/research、/api/synthesis/apply、/api/judgment/update
在此阶段不提供任何 Cognition 写路径。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.errors import SynthesisUnavailableError
from app.synthesis.schemas import SynthesisRequest, SynthesisResponse

router = APIRouter(prefix="/api", tags=["synthesis"])


def _get_service(request: Request):
    svc = getattr(request.app.state, "synthesis", None)
    if svc is None:
        raise SynthesisUnavailableError("synthesis 未启用", detail={"reason": "disabled"})
    return svc


@router.post("/synthesis", response_model=SynthesisResponse)
def synthesize(body: SynthesisRequest, request: Request) -> dict:
    svc = _get_service(request)
    draft = svc.synthesize(body)
    return {"draft": draft}


@router.get("/synthesis/status")
def synthesis_status(request: Request) -> dict:
    """Provider 可用性（Optional Capability §39，供 health/frontend 探活）。"""
    svc = getattr(request.app.state, "synthesis", None)
    if svc is None:
        return {"enabled": False, "provider": None, "available": False}
    from app.core.config import load_config

    cfg = getattr(request.app.state, "cfg", None) or load_config()
    available = svc.provider.is_available()
    return {
        "enabled": True,
        "provider": svc.provider.provider_name,
        "model": cfg.synthesis.model,
        "fallback_model": cfg.synthesis.fallback_model or None,
        "prompt_version": cfg.synthesis.prompt_version,
        "available": available,
    }