"""POST /api/synthesis API（主计划 §14/§15，L1A 只 read+generate+return）。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.errors import (
    AppError,
    EvidenceNotFoundError,
    SynthesisUnavailableError,
)
from app.synthesis.provider import MockProvider, SynthesisProvider
from app.synthesis.schemas import EvidenceRef, SynthesisRequest
from app.synthesis.service import SynthesisService


def _make_app(cfg, conn):
    from fastapi.responses import JSONResponse as _JR

    from app.api import synthesis
    from app.synthesis.grounding import EvidenceResolver

    app = FastAPI()
    app.state.cfg = cfg
    app.state.synthesis = SynthesisService(cfg, MockProvider(cfg.synthesis),
                                           EvidenceResolver(cfg, conn, None))
    app.include_router(synthesis.router)

    @app.exception_handler(AppError)
    async def _handler(request, exc: AppError):
        return _JR(status_code=exc.http_status,
                   content={"error": exc.code, "message": str(exc), "detail": exc.detail})
    return app


def test_synthesize_ok(seeded):
    app = _make_app(seeded["cfg"], seeded["conn"])
    with TestClient(app) as client:
        resp = client.post("/api/synthesis", json={
            "task_type": "summary",
            "query": "HBM4 位宽综合",
            "evidence_refs": [{"source_type": "report", "document_id": "M04",
                               "chunk_id": c} for c in seeded["chunk_ids"]],
            "cognition_context": ["既有判断：先进封装价值提升"],
        })
    assert resp.status_code == 200
    data = resp.json()["draft"]
    assert data["schema_version"] == "1.0"
    assert data["status"] == "draft"
    assert data["claims"]
    assert any("M04:ch1:0001" in c["evidence_refs"] for c in data["claims"])


def test_evidence_not_found_returns_404(seeded):
    app = _make_app(seeded["cfg"], seeded["conn"])
    with TestClient(app) as client:
        resp = client.post("/api/synthesis", json={
            "task_type": "summary", "query": "q",
            "evidence_refs": [{"source_type": "report", "document_id": "M04",
                               "chunk_id": "M04:ch1:NOPE"}],
        })
    assert resp.status_code == 404
    assert resp.json()["error"] == "EVIDENCE_NOT_FOUND"


def test_status_when_enabled(seeded):
    app = _make_app(seeded["cfg"], seeded["conn"])
    with TestClient(app) as client:
        resp = client.get("/api/synthesis/status")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert resp.json()["provider"] == "mock"


def test_status_disabled():
    # 未启用：synthesis = None
    from app.core.config import Config

    cfg = Config()
    app = FastAPI()
    app.state.synthesis = None  # 模拟未启用
    app.state.cfg = cfg
    from app.api import synthesis
    app.include_router(synthesis.router)

    from app.core.errors import AppError

    @app.exception_handler(AppError)
    async def _h(request, exc):
        return JSONResponse(status_code=exc.http_status,
                            content={"error": exc.code, "message": str(exc)})
    with TestClient(app) as client:
        resp = client.get("/api/synthesis/status")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    with TestClient(app) as client:
        resp = client.post("/api/synthesis", json={
            "task_type": "summary", "query": "q",
            "evidence_refs": [{"source_type": "report", "document_id": "M04",
                               "chunk_id": "M04:ch1:0001"}],
        })
    assert resp.status_code == 503
    assert resp.json()["error"] == "SYNTHESIS_UNAVAILABLE"


def test_unavailable_bubbles_as_503(seeded):
    class Down(SynthesisProvider):
        provider_name = "down"
        def chat(self, messages, *, model=None):
            raise SynthesisUnavailableError("down")

    from app.api import synthesis
    from app.synthesis.grounding import EvidenceResolver

    app = FastAPI()
    app.state.cfg = seeded["cfg"]
    app.state.synthesis = SynthesisService(seeded["cfg"], Down(seeded["cfg"].synthesis),
                                           EvidenceResolver(seeded["cfg"], seeded["conn"], None))
    app.include_router(synthesis.router)

    @app.exception_handler(AppError)
    async def _h(request, exc):
        return JSONResponse(status_code=exc.http_status,
                            content={"error": exc.code, "message": str(exc)})
    with TestClient(app) as client:
        resp = client.post("/api/synthesis", json={
            "task_type": "summary", "query": "q",
            "evidence_refs": [{"source_type": "report", "document_id": "M04",
                               "chunk_id": seeded["chunk_ids"][0]}],
        })
    assert resp.status_code == 503
    assert resp.json()["error"] == "SYNTHESIS_UNAVAILABLE"