"""Deterministic research-gap / next-topic candidate API (DL-05A)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.research.gap_candidates import GapCandidateService, TopicCandidateReviewInput

router = APIRouter(
    prefix="/api/research-os/dossiers/{dossier_id}/topic-candidates",
    tags=["research-os-topic-candidates"],
)


def _service(request: Request) -> GapCandidateService:
    app = request.app
    importer = getattr(app.state, "taskpack_importer", None)
    if importer is None:
        raise HTTPException(status_code=503, detail="TaskPack importer unavailable")
    cog = getattr(app.state, "cognition", None) or {}
    cognition_conn = cog.get("conn") if cog.get("enabled") else None
    return GapCandidateService(app.state.cfg, app.state.conn, cognition_conn, importer)


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


@router.post("/refresh")
def refresh_topic_candidates(dossier_id: str, request: Request) -> dict:
    try:
        report = _service(request).refresh(dossier_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "refresh": report.model_dump(mode="json"),
        "auto_create_topic": False,
        "auto_apply": False,
        "formal_write_performed": False,
    }


@router.get("")
def list_topic_candidates(dossier_id: str, request: Request) -> dict:
    try:
        candidates = _service(request).list_candidates(dossier_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "candidates": [item.model_dump(mode="json") for item in candidates],
        "count": len(candidates),
        "formal_write_performed": False,
    }


@router.get("/{candidate_id}")
def get_topic_candidate(dossier_id: str, candidate_id: str, request: Request) -> dict:
    try:
        candidate = _service(request).get(dossier_id, candidate_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "candidate": candidate.model_dump(mode="json"),
        "formal_write_performed": False,
    }


@router.post("/{candidate_id}/review")
def review_topic_candidate(
    dossier_id: str,
    candidate_id: str,
    body: TopicCandidateReviewInput,
    request: Request,
) -> dict:
    try:
        candidate = _service(request).review(dossier_id, candidate_id, body)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "candidate": candidate.model_dump(mode="json"),
        "selected_for_research": candidate.status == "accepted",
        "auto_create_topic": False,
        "auto_apply": False,
        "formal_write_performed": False,
    }
