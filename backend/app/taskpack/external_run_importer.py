"""受控导入外部 TaskPack 候选集到评估 runs。

该入口只负责把已完成的外部回包物化为一个不可部分可见的 run；不会写入
Cognition/Proposal，也不会修改 source taskpack 或已有 run。
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from app.core.config import Config
from app.taskpack.importer import GateResult, ImportReport, TaskPackImporter
from app.taskpack.schemas import is_safe_task_id

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_RESULT_FILES = ("result/result.json", "result/run_meta.json", "result/DONE")


class _PreflightImporter(TaskPackImporter):
    """Run validation without writing INVALID markers or requiring live catalog data."""

    def _mark_invalid(self, pack: Path, report: ImportReport) -> None:  # type: ignore[override]
        return None

    def _gate_stale(self, pack: Path) -> list[GateResult]:  # type: ignore[override]
        # External golden runs are evaluated against their fixed evidence snapshot.
        return [GateResult("stale", True)]


def _validate_task_set(source: Path, expected_ids: list[str]) -> None:
    if not source.is_dir():
        raise ValueError(f"候选目录不存在: {source}")
    actual = sorted(p.name for p in source.iterdir() if p.is_dir())
    if actual != sorted(expected_ids):
        raise ValueError(f"任务集合不匹配: expected={sorted(expected_ids)}, actual={actual}")
    for task_id in expected_ids:
        if not is_safe_task_id(task_id):
            raise ValueError(f"任务 ID 不安全: {task_id}")
        pack = source / task_id
        for rel in _RESULT_FILES:
            if not (pack / rel).is_file():
                raise ValueError(f"{task_id} 缺少 {rel}")


def _preflight(importer: TaskPackImporter, pack: Path) -> ImportReport:
    report = importer.import_task(pack)
    if not report.passed:
        failure = report.first_failure
        reason = failure.failure if failure else "未知 Gate 失败"
        raise ValueError(f"{pack.name} 预校验失败: {reason}")
    return report


def import_external_run(
    source: Path,
    runs_root: Path,
    run_id: str,
    *,
    cfg: Config | None = None,
    expected_ids: list[str] | None = None,
) -> Path:
    """原子导入一个外部候选集，返回正式 run 路径。

    所有候选包先复制到 runs 同卷的临时 stage，并逐项使用既有 Importer 校验；
    仅当全部通过时才 rename 为目标目录。目标已存在或任一步失败均不覆盖目标。
    """
    if not _RUN_ID_RE.fullmatch(run_id) or not is_safe_task_id(run_id):
        raise ValueError(f"run_id 不安全: {run_id}")
    ids = expected_ids or [f"task_{i:03d}" for i in range(1, 33)]
    _validate_task_set(source, ids)
    runs_root = runs_root.resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    target = runs_root / run_id
    if target.exists():
        raise FileExistsError(f"目标 run 已存在: {target}")

    stage = runs_root / f".{run_id}.stage-{uuid.uuid4().hex}"
    importer = _PreflightImporter(cfg or Config(), None, None)
    try:
        stage.mkdir()
        for task_id in ids:
            shutil.copytree(source / task_id, stage / task_id)
            _preflight(importer, stage / task_id)
        if target.exists():
            raise FileExistsError(f"目标 run 已存在: {target}")
        stage.rename(target)
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)
