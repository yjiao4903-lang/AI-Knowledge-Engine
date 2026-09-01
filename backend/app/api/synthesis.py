"""Synthesis TaskPack API（V3.0 方案 §34-§36）。

废弃旧的同步 POST /api/synthesis（.py 不再注册；见 Task 1 移除 LLM runtime）。
新增：
    POST /api/synthesis/tasks                 创建 TaskPack（立即返回 READY）
    GET  /api/synthesis/tasks                 列出全部任务（Task Center，§38）
    GET  /api/synthesis/tasks/{task_id}       单任务详情
    POST /api/synthesis/tasks/{task_id}/rescan 触发 Watcher 导入（§43）
    POST /api/synthesis/tasks/{task_id}/archive 归档（§40）

禁止：POST /api/synthesis/run-model（已随 Task 1 移除）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.core.errors import AppError, EvidenceNotFoundError, EvidenceStaleError
from app.synthesis.schemas import EvidenceRef, SynthesisRequest
from app.taskpack.builder import TaskPackBuilder
from app.taskpack.importer import (
    ARCHIVED,
    COMPLETED,
    IMPORTED,
    INVALID_RESULT,
    READY,
    TaskPackImporter,
)

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])


def _taskpack(request: Request) -> tuple[TaskPackBuilder, TaskPackImporter] | None:
    """按状态引用已构造的 Builder/Importer；未启用或未初始化时返回 None。"""
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
    # 已完成或已导入：附带 result.json 视图（stale 允许查看 snapshot，§48）
    if info.status in (COMPLETED, IMPORTED):
        result_path = pack / "result" / "result.json"
        if result_path.exists():
            try:
                detail["result"] = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                detail["result"] = None
    return detail


@router.post("/tasks")
def create_task(body: SynthesisRequest, request: Request) -> dict:
    """创建 TaskPack，立即返回 READY（§34）。"""
    builder, _ = _require_taskpack(request)
    try:
        created = builder.create_task(
            task_type=body.task_type,
            query=body.query,
            evidence_refs=body.evidence_refs,
            cognition_context=body.cognition_context or None,
        )
    except (EvidenceNotFoundError, EvidenceStaleError, AppError) as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "task_id": created.task_id,
        "status": READY,
        "task_path": str(created.task_path),
    }


@router.get("/tasks")
def list_tasks(request: Request) -> dict:
    """Task Center 列表（§38）：先触发一次 Watcher 扫描，再返回全部状态。"""
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


@router.post("/tasks/{task_id}/rescan")
def rescan_task(task_id: str, request: Request) -> dict:
    """触发对单个任务的 Watcher 导入（§43：前端轮询时触发 scan）。"""
    pack, importer = _require_task(request, task_id)
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
        # Archive collision is a client-visible conflict; source task remains intact.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task_id": task_id, "status": ARCHIVED, "task_path": str(target)}


@router.post("/tasks/{task_id}/open-folder")
def open_task_folder(task_id: str, request: Request) -> dict:
    """"打开任务目录"（§39）：白名单校验根目录内路径后调用系统文件管理器。

    复用 KE 既有 open-original 的受控打开思想，但校验基准是 TaskPack 根目录
    （cfg.taskpack.root_dir），而非知识库 roots。禁止任意路径执行。
    """
    pack, importer = _require_task(request, task_id)
    root = importer.root.resolve()
    resolved = pack.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="path outside taskpack root") from None
    if ".." in relative.parts or not resolved.is_dir():
        raise HTTPException(status_code=403, detail="path outside taskpack root")
    os.startfile(str(resolved))  # noqa: S606 - 本地单用户系统，路径已过白名单校验
    return {"opened": True, "path": str(resolved)}


@router.get("/tasks/{task_id}/prompt")
def get_task_prompt(task_id: str, request: Request) -> dict:
    """复制启动提示词（§38）：返回 AGENT_INSTRUCTION.md 明文。

    纯只读；提示词必须与任务目录内实际文件一致（prompt_sha Gate 校验对象）。
    """
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


# 明文标记：废弃端点不再注册（保留符号以便定位，不挂路由）
_DEPRECATED_SYNC_SYNTHESIS = "POST /api/synthesis 已废弃（V3.0 改为 TaskPack 外部 Worker）"
