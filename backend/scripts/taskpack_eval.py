"""TaskPack 评估（V3.0 方案 §54-§57/§74，Task 10 自动部分）。

**不调用任何模型**。只读取：
- Golden inputs：`data/taskpack_golden/task_001..032/`（含 task.yaml / manifest /
  evidence.jsonl / AGENT_INSTRUCTION.md / output_schema.json）
- Worker results：`data/taskpack_golden/runs/<worker>/<task_id>/result/result.json`
  （按 Importer 认定任务包的方式，把每个 run 目录当作一个任务包读取）

无模型指标（§55/§74 自动部分）：
- Manifest 100% valid
- Result Schema 100% valid
- Citation Invalid Tasks = 0
- Citation Coverage >= 95%
- Unsupported Claim Rate <= 5%

并输出人工 Entailment 审核表（§56：>=50 claim-evidence pairs）。

思路：复用 TaskPackImporter 的八步 Gate（import_task）对每个任务包做导入校验。
为避免写坏已导入目录，改用只读方式——Importer 的 import_task 会在失败时写
INVALID marker，因此这里对每个 run 目录用独立的临时任务包根做拷贝或直接复用一个
只读 Importer 子类（重写 _mark_invalid 为 no-op），确保评估不污染 golden 输入。

输出：docs/TASKPACK_EVALUATION.md（默认），可 --out 指定。

用法（在 project root）：.venv\\Scripts\\python.exe backend\\scripts\\taskpack_eval.py --runs runs/qwen3.8-flash
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import Config  # noqa: E402
from app.taskpack.importer import TaskPackImporter  # noqa: E402


class ReadonlyImporter(TaskPackImporter):
    """评估用只读 Importer：import_task 失败时不写 INVALID marker，不污染输入。

    另将 stale Gate 视为非阻断：评估质控聚焦 §74 自动 Gate（manifest/schema/
    citation 合法性/coverage/unsupported），stale 仅作展示提示（§48 本就不自动改写）。
    """

    def _mark_invalid(self, pack: Path, report) -> None:  # type: ignore[override]
        return None

    def _gate_stale(self, pack: Path):  # type: ignore[override]
        from app.taskpack.importer import GateResult

        return [GateResult("stale", True)]


@dataclass
class TaskMetric:
    task_id: str
    task_type: str | None
    passed: bool
    manifest_valid: bool = False
    schema_valid: bool = False
    citation_invalid: int = 0
    citation_coverage: float | None = None
    unsupported_claim_rate: float | None = None
    stale: bool = False
    errors: list[str] = field(default_factory=list)


def _collect(importer: ReadonlyImporter, runs_root: Path) -> list[TaskMetric]:
    """遍历 runs 目录下每个任务包，逐个跑八步 Gate（只读）。"""
    metrics: list[TaskMetric] = []
    for pack in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        if not (pack / "result" / "result.json").exists():
            metrics.append(TaskMetric(task_id=pack.name, task_type=None, passed=False,
                                      errors=["缺 result/result.json"]))
            continue
        report = importer.import_task(pack)
        m = TaskMetric(
            task_id=report.task_id,
            task_type=None,
            passed=report.passed,
            manifest_valid=report.gates[0].passed if report.gates else False,
            schema_valid=report.schema_valid,
            citation_invalid=report.citation_invalid,
            citation_coverage=report.citation_coverage,
            unsupported_claim_rate=report.unsupported_claim_rate,
            stale=report.stale,
            errors=[f"{g.name}:{g.failure}" for g in report.gates if not g.passed],
        )
        metrics.append(m)
    return metrics


def _entailment_rows(importer: ReadonlyImporter, runs_root: Path) -> list[dict]:
    """提取全部 fact claim-evidence 对（供人工 Entailment 审核，§56）。"""
    rows: list[dict] = []
    for pack in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        rp = pack / "result" / "result.json"
        if not rp.exists():
            continue
        try:
            raw = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            continue
        claims = raw.get("claims") or []
        for c in claims:
            if c.get("epistemic_state") == "uncertain":
                continue
            for ref in (c.get("evidence_refs") or []):
                rows.append({
                    "task_id": pack.name,
                    "claim_id": c.get("id"),
                    "claim_text": (c.get("text") or "")[:160],
                    "epistemic_state": c.get("epistemic_state"),
                    "evidence_chunk_id": ref,
                    "entailment": "",  # 人工：rides / supports / contradicts / unknown
                    "note": "",
                })
    return rows


def _fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def _render(metrics: list[TaskMetric], worker: str, n: int, rows: list[dict]) -> str:
    passed = [m for m in metrics if m.passed]
    cov_ok = [m for m in metrics if m.citation_coverage is not None and m.citation_coverage >= 0.95]
    unsup_ok = [m for m in metrics if m.unsupported_claim_rate is not None and m.unsupported_claim_rate <= 0.05]
    no_invalid = [m for m in metrics if m.citation_invalid == 0]
    manifest_ok = [m for m in metrics if m.manifest_valid]
    schema_ok = [m for m in metrics if m.schema_valid]

    L: list[str] = [f"""# TaskPack Evaluation Report（{worker}）

日期：生成于运行时刻 ｜ 模型：外部 Worker（本报告只做无模型校验）
Golden 输入：`data/taskpack_golden/` ｜ Worker 结果：`data/taskpack_golden/runs/{worker}/`
N = {n} 个任务包

## 汇总（§74 自动 Gate）

| Gate | 要求 | 本 Run |
|---|---|---|
| TaskPack Manifest 100% valid | =N | {len(manifest_ok)}/{n} |
| Result Schema 100% valid | =N | {len(schema_ok)}/{n} |
| Citation Invalid Tasks | =0 | {sum(m.citation_invalid for m in metrics)} |
| Citation Coverage >=95% | >=N | {len(cov_ok)}/{n} |
| Unsupported Claim Rate <=5% | <=N | {len(unsup_ok)}/{n} |
| 全通过 | — | {len(passed)}/{n} |
"""]
    L.append("## 逐任务指标\n\n| task_id | manifest | schema | citation_invalid | cov | unsup | stale | 通过 | 失败 Gate |\n|---|---|---|---|---|---|---|---|---|\n")
    for m in metrics:
        L.append(
            f"| {m.task_id} | {'✓' if m.manifest_valid else '✗'} "
            f"| {'✓' if m.schema_valid else '✗'} | {m.citation_invalid} "
            f"| {_fmt_pct(m.citation_coverage)} | {_fmt_pct(m.unsupported_claim_rate)} "
            f"| {'Y' if m.stale else '—'} | {'PASS' if m.passed else 'FAIL'} | {', '.join(m.errors[:3])} |"
        )

    L.append(f"\n## 人工 Entailment 审核表（§56）")

    if rows:
        L.append(
            "\n需要人工标注：每行 evidence 是否 entail 该 claim（rides / supports / "
            "contradicts / unknown）与备注。\n\n"
            "| task_id | claim_id | epistemic | claim_text | evidence_chunk_id | entailment | note |\n"
            "|---|---|---|---|---|---|---|\n"
        )
        for r in rows:
            L.append(
                f"| {r['task_id']} | {r['claim_id']} | {r['epistemic_state']} "
                f"| {r['claim_text']} | {r['evidence_chunk_id']} | {r['entailment']} | {r['note']} |"
            )
    else:
        L.append("\n无 fact claim（或未发现 result），无需人工标注。")

    L.append(f"\n---\n\n注：本报告不调用模型，仅按 TaskPack Importer 八步 Gate 校验。\n")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="TaskPack 无模型评估（§55/§74）")
    ap.add_argument("--runs", default="runs/qwen3.8-flash",
                    help="runs 目录名（相对 data/taskpack_golden/）")
    ap.add_argument("--root", default=None, help="taskpack_golden 根目录（默认 PROJECT_ROOT/data/taskpack_golden）")
    ap.add_argument("--out", default=None, help="输出 md 路径（默认 docs/TASKPACK_EVALUATION.md）")
    args = ap.parse_args()

    golden_root = Path(args.root) if args.root else PROJECT_ROOT / "data" / "taskpack_golden"
    # 规范化 runs 标识：允许 "runs/<name>" 或 "<name>"
    worker_label = args.runs
    runs_root = golden_root / args.runs
    if worker_label.startswith(("runs/", "runs\\")) or worker_label in ("runs",):
        worker_label = str(Path(args.runs).name)
        runs_root = golden_root / "runs" / worker_label
    if not runs_root.is_dir():
        print(f"未找到 runs 目录: {runs_root}", file=sys.stderr)
        return 2

    # 用只读 Importer：把每个 run 目录当作任务包根，逐任务 import（只读，不写 marker）
    cfg = Config()
    importer = ReadonlyImporter(cfg, None, None)
    importer.root = golden_root  # 覆盖根，使相对路径逻辑可用

    metrics = _collect(importer, runs_root)
    rows = _entailment_rows(importer, runs_root)
    md = _render(metrics, worker_label, len(metrics), rows)

    out = Path(args.out) if args.out else PROJECT_ROOT / "docs" / "TASKPACK_EVALUATION.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())