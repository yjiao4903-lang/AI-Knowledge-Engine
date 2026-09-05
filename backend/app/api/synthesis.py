"""Synthesis TaskPack API（V3.0 + Personal Research OS）。

Task creation accepts explicit Evidence, optional Topic Dossier identity and
explicit Cognition stable IDs. Evidence/Cognition text is always re-resolved on
the server. Proposal publication remains staging-only; Cognition is still the
only formal cognition writer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.errors import AppError, EvidenceNotFoundError, EvidenceStaleError
from app.integration.proposals import build_cognition_proposal_payload
from app.research.context_pack import build_research_context, resolve_cognition_context
from app.research.dossier import TopicDossierService
from app.synthesis.schemas import SynthesisRequest
from app.taskpack.builder import TaskPackBuilder
from app.taskpack.importer import (
    ARCHIVED,
    COMPLETED,
    IMPORTED,
    INVALID_RESULT,
    READY,
    TaskPackImporter,
)
from app.taskpack.launcher import (
    ExternalWorkerLauncher,
    LauncherKind,
    LauncherStateError,
    LauncherUnavailableError,
)
from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])


class LaunchWorkerRequest(BaseModel):
    launcher: LauncherKind


def _taskpack(request: Request) -> tuple[TaskPackBuilder, TaskPackImporter] | None:
    cfg = getattr(request.app.state, "cfg", None)
    if cfg is None or not cfg.taskpack.enabled:
        return None
    builder = getattr(request.app.state, "taskpack_builder", None)
    importer = getattr(request.app.state, "taskpack_importer", None)
    if builder is None or importer is None:
        return None
    return builder, importer


def _require_taskpack(request: Request):
    tp = _taskpack(request)
    if tp is None:
        raise HTTPException(status_code=503, detail="TaskPack 未启用或未初始化")
    return tp


def _require_task(request: Request, task_id: str):
    _, importer = _require_taskpack(request)
    if not task_id or "/" in task_id or "\\" in task_id or ".." in task_id:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    pack = importer.locate(task_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return pack, importer


def _cognition_conn(request: Request):
    cog = getattr(request.app.state, "cognition", None) or {}
    if not cog.get("enabled"):
        return None
    return cog.get("conn")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"无法解析 {path.name}: {exc}") from exc


def _read_taskpack_evidence(pack: Path) -> list[TaskPackEvidence]:
    path = pack / "evidence.jsonl"
    if not path.exists():
        raise HTTPException(status_code=422, detail="evidence.jsonl 缺失")
    evidence: list[TaskPackEvidence] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            evidence.append(TaskPackEvidence.model_validate_json(line))
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"evidence.jsonl 第 {lineno} 行无效: {exc}",
            ) from exc
    return evidence


def _task_detail(pack: Path, importer: TaskPackImporter) -> dict:
    info = importer._make_task_info(pack)
    detail = {
        "task_id": info.task_id,
        "task_path": info.task_path,
        "status": info.status,
        "task_type": info.task_type,
        "query": info.query,
        "created_at": info.created_at,
        "evidence_count": info.evidence_count,
        "worker": info.worker,
        "model": info.model,
        "completed_at": info.completed_at,
        "stale": info.stale,
        "error": info.error,
    }
    context_path = pack / "research_context.json"
    if context_path.exists():
        try:
            detail["research_context"] = json.loads(context_path.read_text(encoding="utf-8"))
            detail["research_brief_available"] = (pack / "research_brief.md").exists()
        except Exception:
            detail["research_context"] = None
            detail["research_brief_available"] = False
    if info.status in (COMPLETED, IMPORTED, INVALID_RESULT):
        result_path = pack / "result" / "result.json"
        if result_path.exists():
            try:
                detail["result"] = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                detail["result"] = None
    return detail


@router.post("/tasks")
def create_task(body: SynthesisRequest, request: Request) -> dict:
    """Create a READY TaskPack from authoritative Evidence/Cognition snapshots."""

    builder, _ = _require_taskpack(request)
    cfg = request.app.state.cfg
    cog_conn = _cognition_conn(request)
    try:
        selected_cognition = resolve_cognition_context(
            cfg,
            cog_conn,
            body.cognition_object_ids,
            legacy_items=body.cognition_context,
        )

        research_context = None
        dossier_id = (body.dossier_id or "").strip() or None
        if dossier_id is not None:
            dossier_service = TopicDossierService(cfg, request.app.state.conn, cog_conn)
            try:
                dossier_detail = dossier_service.get(dossier_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"研究主题不存在: {dossier_id}") from exc
            research_context = build_research_context(
                dossier_detail,
                task_type=body.task_type,
                query=body.query,
                evidence_context_mode=body.evidence_context_mode,
                selected_cognition=selected_cognition,
            )

        created = builder.create_task(
            task_type=body.task_type,
            query=body.query,
            evidence_refs=body.evidence_refs,
            evidence_context_mode=body.evidence_context_mode,
            cognition_context=selected_cognition or None,
            research_context=research_context,
        )
    except HTTPException:
        raise
    except (EvidenceNotFoundError, EvidenceStaleError, AppError) as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "task_id": created.task_id,
        "status": READY,
        "task_path": str(created.task_path),
        "dossier_id": dossier_id,
        "research_context_included": created.research_context_included,
        "cognition_context_count": created.cognition_context_count,
    }


@router.get("/worker-launchers")
def get_worker_launchers(request: Request) -> dict:
    _, importer = _require_taskpack(request)
    launchers = ExternalWorkerLauncher(importer.root).describe()
    return {
        "launchers": [
            {"id": item.id, "label": item.label, "available": item.available}
            for item in launchers
        ]
    }


@router.post("/tasks/{task_id}/launch-worker")
def launch_worker(task_id: str, body: LaunchWorkerRequest, request: Request) -> dict:
    pack, importer = _require_task(request, task_id)
    status = importer.status_of(pack)
    if status != READY:
        raise HTTPException(status_code=409, detail=f"只有 READY TaskPack 可以启动；当前状态={status}")

    launcher = ExternalWorkerLauncher(importer.root)
    try:
        result = launcher.launch_ready(task_id, body.launcher)
    except LauncherUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LauncherStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"启动外部 Worker 失败: {exc}") from exc

    return {
        "task_id": task_id,
        "launcher": result.launcher,
        "launched": True,
        "pid": result.pid,
        "status": "PROCESSING",
        "task_path": str(result.task_path),
    }


@router.get("/tasks")
def list_tasks(request: Request) -> dict:
    _, importer = _require_taskpack(request)
    importer.scan()
    tasks = [{
        "task_id": t.task_id,
        "task_path": t.task_path,
        "status": t.status,
        "task_type": t.task_type,
        "query": t.query,
        "created_at": t.created_at,
        "evidence_count": t.evidence_count,
        "worker": t.worker,
        "model": t.model,
        "completed_at": t.completed_at,
        "stale": t.stale,
        "error": t.error,
    } for t in importer.list_tasks()]
    return {"tasks": tasks, "count": len(tasks)}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request) -> dict:
    pack, importer = _require_task(request, task_id)
    return _task_detail(pack, importer)


@router.get("/tasks/{task_id}/proposal-candidates")
def get_proposal_candidates(task_id: str, request: Request) -> dict:
    """Convert a validated TaskPack result to a Cognition Proposal candidate payload."""

    pack, importer = _require_task(request, task_id)
    info = importer._make_task_info(pack)
    if info.status not in (COMPLETED, IMPORTED):
        raise HTTPException(
            status_code=409,
            detail=f"只有通过 TaskPack Gate 的任务可生成 Proposal 候选；当前状态={info.status}",
        )
    result_path = pack / "result" / "result.json"
    if not result_path.exists():
        raise HTTPException(status_code=422, detail="result/result.json 缺失")
    try:
        result = ResultEnvelope.model_validate(_read_json(result_path))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"result.json 不符合 ResultEnvelope: {exc}") from exc
    evidence = _read_taskpack_evidence(pack)
    payload, warnings = build_cognition_proposal_payload(result, evidence)
    return {
        "task_id": task_id,
        "source_status": info.status,
        "auto_apply": False,
        "target_contract": "Cognition Proposal API V0.2 / POST /api/proposals",
        "proposal_payload": payload,
        "warnings": warnings,
    }


@router.post("/tasks/{task_id}/rescan")
def rescan_task(task_id: str, request: Request) -> dict:
    _pack, importer = _require_task(request, task_id)
    report = importer.rescan_task(task_id)
    if report is None:
        raise HTTPException(status_code=400, detail="任务尚无 result/DONE，无法导入")
    return {
        "task_id": task_id,
        "passed": report.passed,
        "status": COMPLETED if report.passed else INVALID_RESULT,
        "gates": [{"name": g.name, "passed": g.passed, "failure": g.failure} for g in report.gates],
        "stale": report.stale,
        "citation_coverage": report.citation_coverage,
        "unsupported_claim_rate": report.unsupported_claim_rate,
    }


@router.post("/tasks/{task_id}/archive")
def archive_task(task_id: str, request: Request) -> dict:
    _, importer = _require_task(request, task_id)
    try:
        target = importer.archive_task(task_id)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task_id": task_id, "status": ARCHIVED, "task_path": str(target)}


@router.post("/tasks/{task_id}/open-folder")
def open_task_folder(task_id: str, request: Request) -> dict:
    pack, importer = _require_task(request, task_id)
    root = importer.root.resolve()
    resolved = pack.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="path outside taskpack root") from None
    if ".." in relative.parts or not resolved.is_dir():
        raise HTTPException(status_code=403, detail="path outside taskpack root")
    os.startfile(str(resolved))  # noqa: S606 - local single-user app; root already checked
    return {"opened": True, "path": str(resolved)}


@router.get("/tasks/{task_id}/prompt")
def get_task_prompt(task_id: str, request: Request) -> dict:
    pack, _ = _require_task(request, task_id)
    instr = pack / "AGENT_INSTRUCTION.md"
    if not instr.exists():
        raise HTTPException(status_code=404, detail="AGENT_INSTRUCTION.md 缺失")
    return {
        "task_id": task_id,
        "file": "AGENT_INSTRUCTION.md",
        "content": instr.read_text(encoding="utf-8"),
        "sha256": sha256_file_wrapper(instr),
    }


def sha256_file_wrapper(path: Path) -> str:
    from app.taskpack.manifest import sha256_file

    return sha256_file(path)


_DEPRECATED_SYNC_SYNTHESIS = "POST /api/synthesis 已废弃（V3.0 改为 TaskPack 外部 Worker）"
