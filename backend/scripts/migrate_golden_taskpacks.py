"""32 Golden → Golden TaskPack 迁移（V3.0 方案 §53-§54/§71，Task 7 外部执行先于 Task 9）。

把 `data/synthesis_golden_tasks.jsonl` 的 32 条固定 Golden 输入转换为
`data/taskpack_golden/task_001..task_032/` 固定 TaskPack（只读输入包）。

- 复用一个隔离的 TaskPackBuilder：golden root 作为 cfg.taskpack.root_dir，
  每条通过 builder.create_task 生成（Evidence Set 由 KE catalog 权威解析，
  与 Builder 完全一致，§9），再移动到 task_001.. 目录。
- 不改变原 Evidence Set：evidence.jsonl 由 EvidenceResolver 按 chunk_id 解析，
  只读复用 catalog，不新增/删除证据（§53）。
- 生成后未调用任何模型（Task 9 由用户外部执行）。

用法（在 project root）：
    .venv\\Scripts\\python.exe backend\\scripts\\migrate_golden_taskpacks.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import Config, load_config  # noqa: E402
from app.synthesis.schemas import EvidenceRef, SynthesisRequest  # noqa: E402
from app.storage.migrations import init_schema  # noqa: E402
from app.storage.sqlite import connect  # noqa: E402
from app.taskpack.builder import TaskPackBuilder  # noqa: E402

GOLDEN_SOURCE = PROJECT_ROOT / "data" / "synthesis_golden_tasks.jsonl"


def main() -> int:
    cfg = load_config()
    golden_root = PROJECT_ROOT / "data" / "taskpack_golden"
    runs_root = golden_root / "runs"
    golden_root.mkdir(parents=True, exist_ok=True)
    runs_root.mkdir(parents=True, exist_ok=True)

    # 隔离 builder root（黄金任务目录即 golden_root），避免触碰生产 outbox。
    build_cfg = Config()
    build_cfg.taskpack.root_dir = str(golden_root)

    # 复用 KE catalog（report 证据 ground truth）
    report_conn = connect(cfg.sqlite.path, check_same_thread=False)
    init_schema(report_conn)

    # cognition catalog（spec：keeps cognition context read-only）；可能不存在，退化 None
    cognition_conn = None
    if cfg.cognition.enabled and cfg.cognition.catalog_path:
        cog_path = Path(cfg.cognition.catalog_path)
        if cog_path.exists():
            from app.storage.sqlite import connect as _c
            cognition_conn = _c(str(cog_path), check_same_thread=False)

    builder = TaskPackBuilder(build_cfg, report_conn, cognition_conn)

    lines = [l for l in GOLDEN_SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) != 32:
        print(f"警告：Golden 源应有 32 条，实际 {len(lines)}", file=sys.stderr)

    created = []
    for i, line in enumerate(lines, start=1):
        src = json.loads(line)
        task_dir = golden_root / f"task_{i:03d}"
        if task_dir.is_dir():
            # 幂等：已存在则跳过重建
            created.append({"index": i, "task_id": task_dir.name, "skipped": True})
            continue
        req = SynthesisRequest(
            task_type=src["task_type"],
            query=src["query"],
            evidence_refs=[EvidenceRef.model_validate(r) for r in src["evidence_refs"]],
        )
        created_task = builder.create_task(
            task_type=req.task_type,
            query=req.query,
            evidence_refs=req.evidence_refs,
            cognition_context=None,
        )
        shutil.move(str(created_task.task_path), str(task_dir))
        created.append({"index": i, "task_id": created_task.task_id, "task_dir": str(task_dir)})
        report_conn.commit()  # 无需写库，仅刷新事务

    with (golden_root / "README.md").open("w", encoding="utf-8") as f:
        f.write(
            "32 Golden → Golden TaskPack（V3.0 迁移产物）。\n"
            "目录 task_001..task_032 为固定只读输入包；runs/<worker> 存放各模型结果。\n"
            "重新生成：backend/scripts/migrate_golden_taskpacks.py（幂等，已存在跳过）。\n"
        )

    print(f"Golden root: {golden_root}")
    print(f"任务包: {len(created)}（含 skipped）")
    for c in created:
        print(f"  {c['index']:03d}  {c['task_id']}")
    print("完成（未调用任何模型）。下一步由用户外部执行 Task 9：32 golden external run。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())