"""Deterministic research-gap / next-topic candidate API (DL-05)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.contracts.cognition import CognitionContextItem
from app.core.errors import AppError, EvidenceNotFoundError, EvidenceStaleError
from app.research.context_pack import build_research_context, resolve_cognition_context
from app.research.gap_candidates import GapCandidateService, TopicCandidateReviewInput
from app.synthesis.schemas import EvidenceContextMode, EvidenceRef
from app.taskpack.importer import READY

router = APIRouter(
    prefix="/api/research-os/dossiers/{dossier_id}/topic-candidates",
    tags=["research-os-topic-candidates"],
)


class CandidateTaskRequest(BaseModel):
    """Evidence/Cognition selections for an accepted next-research candidate.

    The candidate's research question and planning fields are re-read server-side;
    the browser cannot replace them. This endpoint only creates/reuses a TaskPack.
    """

    task_type: Literal["summary", "comparison", "causal_synthesis", "tension_extraction"] = "summary"
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    evidence_context_mode: EvidenceContextMode = "none"
    cognition_object_ids: list[str] = Field(default_factory=list, max_length=100)
    cognition_context: list[CognitionContextItem] = Field(default_factory=list)


def _service(request: Request) -> GapCandidateService:
    app = request.app
    importer = getattr(app.state, "taskpack_importer", None)
    if importer is None:
        raise HTTPException(status_code=503, detail="TaskPack importer unavailable")
    cog = getattr(app.state, "cognition", None) or {}
    cognition_conn = cog.get("conn") if cog.get("enabled") else None
    return GapCandidateService(app.state.cfg, app.state.conn, cognition_conn, importer)


def _taskpack(request: Request):
    builder = getattr(request.app.state, "taskpack_builder", None)
    importer = getattr(request.app.state, "taskpack_importer", None)
    if builder is None or importer is None:
        raise HTTPException(status_code=503, detail="TaskPack 未启用或未初始化")
    return builder, importer


def _cognition_conn(request: Request):
    cog = getattr(request.app.state, "cognition", None) or {}
    return cog.get("conn") if cog.get("enabled") else None


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


def _find_linked_task(importer, dossier_id: str, candidate_id: str):
    """Return the first TaskPack already linked to this accepted candidate.

    TaskPack status remains the execution state machine. We do not add a second
    candidate execution state or create another task for repeated submissions.
    """

    for info in importer.list_tasks():
        pack = importer.locate(info.task_id)
        if pack is None:
            continue
        context_path = Path(pack) / "research_context.json"
        if not context_path.exists():
            continue
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        direction = context.get("direction") or {}
        task = context.get("task") or {}
        if (
            direction.get("dossier_id") == dossier_id
            and task.get("topic_candidate_id") == candidate_id
        ):
            return info, pack
    return None


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
        "max_candidates": 5,
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


@router.post("/{candidate_id}/task")
def create_or_reuse_candidate_task(
    dossier_id: str,
    candidate_id: str,
    body: CandidateTaskRequest,
    request: Request,
) -> dict:
    """Create one DL-03 TaskPack for an accepted card, or reuse its existing one.

    This endpoint deliberately has no launcher parameter and never calls the
    external Worker launcher. A user must start a READY TaskPack separately.
    """

    service = _service(request)
    try:
        candidate = service.get(dossier_id, candidate_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    if candidate.status != "accepted":
        raise HTTPException(
            status_code=409,
            detail="只有已选入下一轮（accepted）的候选可以创建 TaskPack",
        )

    builder, importer = _taskpack(request)
    existing = _find_linked_task(importer, dossier_id, candidate_id)
    if existing is not None:
        info, pack = existing
        return {
            "task_id": info.task_id,
            "status": info.status,
            "task_path": str(pack),
            "dossier_id": dossier_id,
            "topic_candidate_id": candidate_id,
            "query": candidate.research_question,
            "reused": True,
            "worker_launched": False,
            "auto_apply": False,
            "formal_write_performed": False,
        }

    cfg = request.app.state.cfg
    cog_conn = _cognition_conn(request)
    try:
        selected_cognition = resolve_cognition_context(
            cfg,
            cog_conn,
            body.cognition_object_ids,
            legacy_items=body.cognition_context,
        )
        dossier_detail = service.dossiers.get(dossier_id)
        context = build_research_context(
            dossier_detail,
            task_type=body.task_type,
            query=candidate.research_question,
            evidence_context_mode=body.evidence_context_mode,
            selected_cognition=selected_cognition,
            topic_candidate=candidate.model_dump(mode="json"),
        )
        created = builder.create_task(
            task_type=body.task_type,
            query=candidate.research_question,
            evidence_refs=body.evidence_refs,
            evidence_context_mode=body.evidence_context_mode,
            cognition_context=selected_cognition or None,
            research_context=context,
        )
    except KeyError as exc:
        raise _not_found(exc) from exc
    except (EvidenceNotFoundError, EvidenceStaleError, AppError) as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "task_id": created.task_id,
        "status": READY,
        "task_path": str(created.task_path),
        "dossier_id": dossier_id,
        "topic_candidate_id": candidate_id,
        "query": candidate.research_question,
        "research_context_included": created.research_context_included,
        "cognition_context_count": created.cognition_context_count,
        "reused": False,
        "worker_launched": False,
        "auto_apply": False,
        "formal_write_performed": False,
    }
