"""Research-return staging plus explicit Cognition Formal Handoff API.

Staging review remains KE-owned. Formal operations are separate endpoints and use
only the verified local Cognition HTTP contract: Proposal create -> Preview ->
explicit Human Apply. KE never writes Cognition Markdown/SQLite directly.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from app.integration.cognition_gateway import CognitionGateway, CognitionGatewayError
from app.integration.return_formal import (
    FormalApplyInput,
    FormalCognitionHandoffService,
    FormalHandoffStateError,
    FormalHandoffStore,
)
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


def _gateway(request: Request) -> CognitionGateway:
    cfg = request.app.state.cfg
    return CognitionGateway(
        cfg.cognition.api_url,
        timeout_seconds=cfg.cognition.api_timeout_seconds,
    )


def _response(record, **extra) -> dict:
    """Staging response: acceptance is never equivalent to a formal write."""
    return {
        **extra,
        "return_candidates": record.model_dump(mode="json"),
        "formal_preview_supported": True,
        "formal_apply_supported": bool(
            getattr(getattr(extra.get("request"), "app", None), "state", None)
        ) if False else False,
        "auto_apply": False,
        "formal_write_performed": False,
    }


def _raise(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    if isinstance(exc, (ReturnCandidateStateError, FormalHandoffStateError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, CognitionGatewayError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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


def _refresh_derived_cognition(request: Request) -> None:
    """Synchronize the read-only derived catalog before version-sensitive handoff.

    This reads formal Cognition Markdown and updates only KE's derived SQLite
    projection. It performs no formal Cognition write.
    """
    cog = getattr(request.app.state, "cognition", None) or {}
    conn = cog.get("conn")
    pipeline = cog.get("catalog_pipeline")
    if not cog.get("enabled") or conn is None or pipeline is None:
        return

    from app.cognition.scanner import scan as cognition_scan

    def _run() -> None:
        result = cognition_scan(request.app.state.cfg, conn)
        if result.has_changes:
            pipeline.apply_scan(result)

    lock = getattr(request.app.state, "index_lock", None)
    if lock is None:
        _run()
        return
    with lock:
        _run()


def _formal_context(request: Request, task_id: str, candidate_id: str):
    _refresh_derived_cognition(request)
    service = _service(request)
    try:
        record = service.refresh_target_versions(task_id)
        candidate = _find_candidate(record, candidate_id)
        pack, result, evidence, _context = service._validated_task(task_id)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    return service, record, candidate, pack, result, evidence


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
    """Promote optional Worker suggestions from a Gate-passed result into KE staging."""
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
    _refresh_derived_cognition(request)
    try:
        record = _service(request).refresh_target_versions(task_id)
    except (KeyError, ReturnCandidateStateError, ValueError) as exc:
        _raise(exc)
    return _response(record, count=len(record.candidates))


@router.get("/{candidate_id}/preflight")
def preflight_return_candidate(task_id: str, candidate_id: str, request: Request) -> dict:
    """Refresh targets and expose explainable KE preflight, distinct from Cognition Preview."""
    _refresh_derived_cognition(request)
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
        "formal_preview_supported": True,
        "formal_apply_supported": bool(request.app.state.cfg.cognition.formal_apply_enabled),
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


@router.get("/{candidate_id}/formal-handoff")
def get_formal_handoff(task_id: str, candidate_id: str, request: Request) -> dict:
    try:
        pack = _service(request)._require_task_exists(task_id)
        marker = FormalHandoffStore(pack).read(candidate_id)
    except (KeyError, FormalHandoffStateError) as exc:
        _raise(exc)
    return {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "formal_handoff": marker,
        "formal_apply_supported": bool(request.app.state.cfg.cognition.formal_apply_enabled),
        "auto_apply": False,
        "formal_write_performed": bool(marker and marker.get("formal_write_performed")),
    }


@router.post("/{candidate_id}/formalize")
def formalize_return_candidate(task_id: str, candidate_id: str, request: Request) -> dict:
    """Create one Cognition Proposal item. This endpoint does not Apply it."""
    cfg = request.app.state.cfg
    if not cfg.cognition.proposal_publish_enabled:
        raise HTTPException(status_code=403, detail="Cognition Proposal publication is disabled")
    _svc, _record, candidate, pack, result, evidence = _formal_context(
        request, task_id, candidate_id
    )
    try:
        marker, reused = FormalCognitionHandoffService(_gateway(request)).formalize(
            pack=pack,
            candidate=candidate,
            result=result,
            evidence=evidence,
        )
    except (FormalHandoffStateError, CognitionGatewayError, ValueError) as exc:
        _raise(exc)
    return {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "formal_handoff": marker,
        "reused": reused,
        "formal_preview_supported": True,
        "formal_apply_supported": bool(cfg.cognition.formal_apply_enabled),
        "auto_apply": False,
        "formal_write_performed": False,
    }


@router.post("/{candidate_id}/formal-preview")
def preview_formal_return_candidate(task_id: str, candidate_id: str, request: Request) -> dict:
    """Run Cognition's official zero-write Preview after rechecking target versions."""
    _svc, _record, candidate, pack, _result, _evidence = _formal_context(
        request, task_id, candidate_id
    )
    if candidate.status != "accepted":
        raise HTTPException(status_code=409, detail="return candidate must remain accepted")
    if candidate.has_version_conflict or candidate.version_check_incomplete:
        raise HTTPException(status_code=409, detail="target version preflight is not clean")
    try:
        marker = FormalCognitionHandoffService(_gateway(request)).preview(
            pack=pack,
            candidate=candidate,
        )
    except (FormalHandoffStateError, CognitionGatewayError, ValueError) as exc:
        _raise(exc)
    return {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "formal_handoff": marker,
        "formal_preview_supported": True,
        "formal_apply_supported": bool(request.app.state.cfg.cognition.formal_apply_enabled),
        "auto_apply": False,
        "formal_write_performed": False,
    }


@router.post("/{candidate_id}/formal-apply")
def apply_formal_return_candidate(
    task_id: str,
    candidate_id: str,
    body: FormalApplyInput,
    request: Request,
) -> dict:
    """Explicit Human Apply. Cognition App remains the actual formal writer."""
    cfg = request.app.state.cfg
    if not cfg.cognition.formal_apply_enabled:
        raise HTTPException(
            status_code=403,
            detail=(
                "Formal Apply is disabled. Enable cognition.formal_apply_enabled "
                "or AIKE_COGNITION_FORMAL_APPLY only after local acceptance."
            ),
        )
    _svc, _record, candidate, pack, _result, _evidence = _formal_context(
        request, task_id, candidate_id
    )
    if candidate.status != "accepted":
        raise HTTPException(status_code=409, detail="return candidate must remain accepted")
    if candidate.has_version_conflict or candidate.version_check_incomplete:
        raise HTTPException(status_code=409, detail="target version preflight is not clean")
    try:
        marker = FormalCognitionHandoffService(_gateway(request)).apply(
            pack=pack,
            candidate=candidate,
            body=body,
        )
    except (FormalHandoffStateError, CognitionGatewayError, ValueError) as exc:
        _raise(exc)
    return {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "formal_handoff": marker,
        "writer": "cognition_app",
        "formal_preview_supported": True,
        "formal_apply_supported": True,
        "auto_apply": False,
        "formal_write_performed": True,
    }
