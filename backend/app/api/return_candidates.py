"""Research-return / cognition-change staging API (DL-06A).

All endpoints operate on KE-owned candidate state only. They intentionally expose
no formal Cognition Preview/Apply/Revision operation until the real Cognition
contract has been inspected and verified.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.research.return_candidates import (
    ResearchReturnBatchInput,
    ResearchReturnCandidateService,
    ReturnCandidateReviewInput,
    ReturnCandidateStateError,
)

router = APIRouter(
    prefix="/api/research-os/tasks/{task_id}/return-candidates",
    tags=["research-os-return-candidates"],
)


def _service(request: Request) -> ResearchReturnCandidateService:
    importer = getattr(request.app.state, "taskpack_importer", None)
    if importer is None:
        raise HTTPException(status_code=503, detail="TaskPack importer unavailable")
    cog = getattr(request.app.state, "cognition", None) or {}
    cognition_conn = cog.get("conn") if cog.get("enabled") else None
    return ResearchReturnCandidateService(
        request.app.state.cfg,
        request.app.state.conn,
        cognition_conn,
        importer,
    )


def _response(record, **extra) -> dict:
    return {
        **extra,
        "return_candidates": record.model_dump(mode="json"),
        "formal_preview_supported": False,
        "formal_apply_supported": False,
        "auto_apply": False,
        "formal_write_performed": False,
    }


def _raise(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    if isinstance(exc, ReturnCandidateStateError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.post("")
def ingest_return_candidates(
    task_id: str,
    body: ResearchReturnBatchInput,
    request: Request,
) -> dict:
    try:
        record, created, reused = _service(request).ingest(task_id, body)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    return _response(record, created=created, reused=reused)


@router.get("")
def list_return_candidates(task_id: str, request: Request) -> dict:
    try:
        record = _service(request).list_candidates(task_id)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    return _response(record, count=len(record.candidates))


@router.post("/refresh-targets")
def refresh_return_candidate_targets(task_id: str, request: Request) -> dict:
    try:
        record = _service(request).refresh_target_versions(task_id)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    return _response(record, count=len(record.candidates))


@router.post("/{candidate_id}/review")
def review_return_candidate(
    task_id: str,
    candidate_id: str,
    body: ReturnCandidateReviewInput,
    request: Request,
) -> dict:
    try:
        record = _service(request).review(task_id, candidate_id, body)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    candidate = next(item for item in record.candidates if item.candidate_id == candidate_id)
    return _response(
        record,
        candidate=candidate.model_dump(mode="json"),
        accepted_for_future_preview=candidate.status == "accepted",
    )
