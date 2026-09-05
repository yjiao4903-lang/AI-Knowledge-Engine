"""Reviewable report-increment and relationship candidate API (DL-04A).

This API exposes KE-owned candidate state only. Creating or reviewing a candidate
never writes formal Cognition content and never auto-applies a proposal.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.research.increment_candidates import (
    CandidateReviewInput,
    IncrementAnalysisInput,
    IncrementCandidateService,
)

router = APIRouter(
    prefix="/api/research-os/dossiers/{dossier_id}/increment-analyses",
    tags=["research-os-increment-analysis"],
)


def _service(request: Request) -> IncrementCandidateService:
    app = request.app
    cog = getattr(app.state, "cognition", None) or {}
    cognition_conn = cog.get("conn") if cog.get("enabled") else None
    return IncrementCandidateService(app.state.cfg, app.state.conn, cognition_conn)


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


@router.post("")
def create_increment_analysis(
    dossier_id: str,
    body: IncrementAnalysisInput,
    request: Request,
) -> dict:
    try:
        analysis, reused = _service(request).ingest(dossier_id, body)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "analysis": analysis.model_dump(mode="json"),
        "reused": reused,
        "auto_apply": False,
        "formal_write_performed": False,
    }


@router.get("")
def list_increment_analyses(dossier_id: str, request: Request) -> dict:
    try:
        analyses = _service(request).list_analyses(dossier_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "analyses": [item.model_dump(mode="json") for item in analyses],
        "formal_write_performed": False,
    }


@router.get("/{analysis_id}")
def get_increment_analysis(
    dossier_id: str,
    analysis_id: str,
    request: Request,
) -> dict:
    try:
        analysis = _service(request).get(dossier_id, analysis_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "analysis": analysis.model_dump(mode="json"),
        "formal_write_performed": False,
    }


@router.post("/{analysis_id}/candidates/{candidate_id}/review")
def review_candidate(
    dossier_id: str,
    analysis_id: str,
    candidate_id: str,
    body: CandidateReviewInput,
    request: Request,
) -> dict:
    try:
        analysis = _service(request).review(dossier_id, analysis_id, candidate_id, body)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "analysis": analysis.model_dump(mode="json"),
        "auto_apply": False,
        "formal_write_performed": False,
    }
