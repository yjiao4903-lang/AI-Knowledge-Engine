"""只读外部 TaskPack runs 目录 API。"""
from __future__ import annotations
import json
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_TASK_ID_RE = re.compile(r"^task_[0-9]{3}$")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNS_ROOT = PROJECT_ROOT / "data" / "taskpack_golden" / "runs"
router = APIRouter(prefix="/api/taskpack/runs", tags=["taskpack-runs"])

def _safe_dir(root: Path, name: str) -> Path:
    if not _RUN_ID_RE.fullmatch(name):
        raise HTTPException(status_code=404, detail="run 不存在")
    path = (root / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="run 不存在") from None
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="run 不存在")
    return path

def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None

def _task_summary(task_dir: Path) -> dict:
    result = _read_json(task_dir / "result" / "result.json") or {}
    meta = _read_json(task_dir / "result" / "run_meta.json") or {}
    worker = result.get("worker") if isinstance(result.get("worker"), dict) else {}
    return {
        "task_id": task_dir.name,
        "status": "COMPLETED" if (task_dir / "result" / "DONE").is_file() else "INCOMPLETE",
        "task_type": result.get("task_type"), "query": result.get("query"),
        "worker": meta.get("worker_tool") or worker.get("tool"),
        "model": meta.get("model") or worker.get("model"),
        "completed_at": meta.get("completed_at") or result.get("generated_at"),
        "claims_count": len(result.get("claims", [])) if isinstance(result.get("claims"), list) else 0,
        "tensions_count": len(result.get("tensions", [])) if isinstance(result.get("tensions"), list) else 0,
    }

def _task_dir(run_dir: Path, task_id: str) -> Path:
    if not _TASK_ID_RE.fullmatch(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    path = (run_dir / task_id).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="任务不存在") from None
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="任务不存在")
    return path

@router.get("")
def list_runs() -> dict:
    """列出外部评估 run；只读，不触发 Importer scan。"""
    if not RUNS_ROOT.is_dir():
        return {"runs": [], "count": 0}
    runs = []
    for run_dir in sorted(RUNS_ROOT.iterdir()):
        if not run_dir.is_dir() or not _RUN_ID_RE.fullmatch(run_dir.name):
            continue
        tasks = [p for p in run_dir.iterdir() if p.is_dir() and _TASK_ID_RE.fullmatch(p.name)]
        runs.append({"run_id": run_dir.name, "task_count": len(tasks), "path": str(run_dir)})
    return {"runs": runs, "count": len(runs)}

@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    run_dir = _safe_dir(RUNS_ROOT, run_id)
    tasks = sorted(p for p in run_dir.iterdir() if p.is_dir() and _TASK_ID_RE.fullmatch(p.name))
    return {"run_id": run_id, "path": str(run_dir), "task_count": len(tasks),
            "tasks": [_task_summary(p) for p in tasks]}

@router.get("/{run_id}/{task_id}")
def get_run_task(run_id: str, task_id: str) -> dict:
    run_dir = _safe_dir(RUNS_ROOT, run_id)
    task_dir = _task_dir(run_dir, task_id)
    summary = _task_summary(task_dir)
    result = _read_json(task_dir / "result" / "result.json") or {}
    return {"run_id": run_id, "path": str(task_dir), **summary,
            "schema_version": result.get("schema_version"), "generated_at": result.get("generated_at"),
            "additional_evidence_needed_count": (len(result.get("additional_evidence_needed", []))
                if isinstance(result.get("additional_evidence_needed"), list) else 0)}
