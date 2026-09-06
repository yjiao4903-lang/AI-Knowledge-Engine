"""Research-return / cognition-change staging API (DL-06A/B).

All endpoints operate on KE-owned candidate state only. They intentionally expose
no formal Cognition Preview/Apply/Revision operation until the real Cognition
contract has been inspected and verified.
"""

from __future__ import annotations

import json

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


def _find_candidate(record, candidate_id: str):
    candidate = next(
        (item for item in record.candidates if item.candidate_id == candidate_id),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"return candidate not found: {candidate_id}")
    return candidate


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
    return _response(record, created=created, reused=reused, source="explicit_api")


@router.post("/ingest-result")
def ingest_taskpack_return_suggestions(task_id: str, request: Request) -> dict:
    """Promote optional Worker suggestions from a Gate-passed result into KE staging.

    `research_return_candidates` is an optional backward-compatible result field.
    Its contents are never trusted directly: the same service validation checks
    target Cognition membership, TaskPack Evidence membership, source result IDs,
    and target-version state before persisting a candidate.
    """

    service = _service(request)
    try:
        pack, _result, _evidence, _context = service._validated_task(task_id)
        raw = json.loads((pack / "result" / "result.json").read_text(encoding="utf-8-sig"))
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"cannot read TaskPack result: {exc}") from exc

    suggestions = raw.get("research_return_candidates", [])
    if suggestions is None:
        suggestions = []
    if not isinstance(suggestions, list):
        raise HTTPException(
            status_code=422,
            detail="research_return_candidates must be an array when present",
        )
    if not suggestions:
        try:
            record = service.list_candidates(task_id)
        except (KeyError, ReturnCandidateStateError, ValueError) as exc:
            _raise(exc)
        return _response(
            record,
            created=0,
            reused=0,
            source_candidates=0,
            source="taskpack_result",
        )

    try:
        body = ResearchReturnBatchInput(candidates=suggestions)
        record, created, reused = service.ingest(task_id, body)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"invalid research_return_candidates: {exc}",
        ) from exc
    return _response(
        record,
        created=created,
        reused=reused,
        source_candidates=len(suggestions),
        source="taskpack_result",
    )


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


@router.get("/{candidate_id}/preflight")
def preflight_return_candidate(task_id: str, candidate_id: str, request: Request) -> dict:
    """Refresh targets and expose an explainable KE preflight, not Cognition Preview."""

    try:
        record = _service(request).refresh_target_versions(task_id)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    candidate = _find_candidate(record, candidate_id)
    targets = [
        {
            "object_id": target.object_id,
            "object_type": target.object_type,
            "baseline": {
                "content_hash": target.baseline_content_hash,
                "title": target.baseline_title,
                "excerpt": target.baseline_excerpt,
            },
            "current": {
                "content_hash": target.current_content_hash,
                "title": target.current_title,
                "excerpt": target.current_excerpt,
            },
            "version_state": target.version_state,
            "checked_at": target.checked_at,
        }
        for target in candidate.target_snapshots
    ]
    return {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "intent": candidate.intent,
        "status": candidate.status,
        "proposed_text": candidate.proposed_text,
        "reason": candidate.reason,
        "evidence_chunk_ids": candidate.evidence_chunk_ids,
        "targets": targets,
        "has_version_conflict": candidate.has_version_conflict,
        "version_check_incomplete": candidate.version_check_incomplete,
        "ke_preflight_only": True,
        "formal_preview_supported": False,
        "formal_apply_supported": False,
        "auto_apply": False,
        "formal_write_performed": False,
    }


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
    candidate = _find_candidate(record, candidate_id)
    return _response(
        record,
        candidate=candidate.model_dump(mode="json"),
        accepted_for_future_preview=candidate.status == "accepted",
    )
