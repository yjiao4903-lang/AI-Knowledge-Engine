"""Synthesis Golden Evaluation Harness（主计划 §19-§26，Task 7-8）。

- 读取 data/synthesis_golden_tasks.jsonl（固定 Evidence Set，避免混入 Retrieval 变量）；
- 对每条任务：grounding 解析证据（catalog 权威正文）-> prompt -> provider -> validate；
- 输出 L1A 指标（schema_valid / citation_coverage / unsupported_claim_rate /
  citation_invalid / epistemic 分布）到具体 JSON。

默认用 config 指定 provider（生产为 ollama）；`--provider mock` 可离线跑通全链路
（确定性 MockProvider），`--provider ollama` 可显式指定真实模型。

用法（在 backend/ 下）：
  python scripts/synthesis_golden_eval.py                      # config provider（ollama）
  python scripts/synthesis_golden_eval.py --provider mock      # 离线确定性
  python scripts/synthesis_golden_eval.py --provider ollama --limit 8
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import load_config  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.storage.sqlite import connect  # noqa: E402
from app.synthesis.grounding import EvidenceResolver  # noqa: E402
from app.synthesis.provider import get_provider  # noqa: E402
from app.synthesis.schemas import EvidenceRef, SynthesisRequest  # noqa: E402
from app.synthesis.service import SynthesisService  # noqa: E402
from app.synthesis.validator import validate_draft  # noqa: E402


def _load_tasks(path: Path, limit: int | None) -> list[dict]:
    tasks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            tasks.append(json.loads(line))
    if limit:
        tasks = random.Random(42).sample(tasks, min(limit, len(tasks)))
    return tasks


def run(cfg, tasks: list[dict], provider_name: str, out_dir: Path) -> dict:
    cfg.synthesis.provider = provider_name
    # 只读连接：本 harness 只从 catalog 读取 chunk 正文（Draft 不落库），
    # 绝不写生产库 —— 避免与常驻 uvicorn 的 SQLite 写锁互斥导致无限阻塞。
    report_conn = connect(cfg.sqlite.path, read_only=True, check_same_thread=False)
    cog_conn = None
    if cfg.cognition.enabled:
        try:
            cog_conn = connect(cfg.cognition.catalog_path, read_only=True, check_same_thread=False)
        except Exception:
            cog_conn = None

    resolver = EvidenceResolver(cfg, report_conn, cog_conn)
    provider = get_provider(cfg.synthesis)
    svc = SynthesisService(cfg, provider, resolver)

    results: list[dict] = []
    failures: list[dict] = []
    agg = {
        "provider": provider_name,
        "model": cfg.synthesis.model,
        "prompt_version": cfg.synthesis.prompt_version,
        "tasks_total": len(tasks),
        "tasks_ok": 0,
        "schema_valid": {"count": 0, "total": len(tasks)},
        "citation_invalid_tasks": 0,
        "coverage_values": [],
        "unsupported_values": [],
        "epistemic_counts": {"supported": 0, "inference": 0, "hypothesis": 0,
                             "uncertain": 0, "contradicted": 0},
        "latency_ms": [],
    }

    for idx, task in enumerate(tasks, start=1):
        record = {"index": idx, "task_type": task.get("task_type"),
                  "query": task.get("query"), "evidence_refs": task.get("evidence_refs")}
        started = time.time()
        try:
            req = SynthesisRequest(
                task_type=task["task_type"],
                query=task["query"],
                evidence_refs=[EvidenceRef(**r) for r in task["evidence_refs"]],
            )
            timing: dict = {}
            draft = svc.synthesize(req, timing=timing)
            provided = {r["chunk_id"] for r in task["evidence_refs"]}
            rep = validate_draft(draft, provided)
            record.update({
                "status": "ok",
                "timing": timing,
                "draft_id": draft.id,
                "claims_count": len(draft.claims),
                "schema_valid": rep.schema_valid,
                "factual_claims": rep.factual_claims,
                "citation_coverage": rep.citation_coverage,
                "unsupported_claim_rate": rep.unsupported_claim_rate,
                "citation_invalid": rep.citation_invalid,
                "epistemic": [c.epistemic_state for c in draft.claims],
            })
            agg["tasks_ok"] += 1
            if rep.schema_valid:
                agg["schema_valid"]["count"] += 1
            if rep.citation_invalid:
                agg["citation_invalid_tasks"] += 1
            if rep.citation_coverage is not None:
                agg["coverage_values"].append(rep.citation_coverage)
            if rep.unsupported_claim_rate is not None:
                agg["unsupported_values"].append(rep.unsupported_claim_rate)
            for es in record["epistemic"]:
                agg["epistemic_counts"][es] += 1
            results.append(record)
        except AppError as exc:
            record["status"] = "error"
            record["error_code"] = exc.code
            record["error_message"] = str(exc)
            failures.append(record)
        finally:
            agg["latency_ms"].append(int((time.time() - started) * 1000))

    # 汇总指标
    cov = agg["coverage_values"]
    unsup = agg["unsupported_values"]
    agg["citation_coverage_avg"] = round(sum(cov) / len(cov), 4) if cov else None
    agg["unsupported_claim_rate_avg"] = round(sum(unsup) / len(unsup), 4) if unsup else None
    agg["citation_invalid_tasks"] = sum(1 for r in results if r.get("citation_invalid"))

    # 相位级耗时/计量聚合（provider 计量能力可用时）
    t_rows = [r.get("timing") for r in results
              if r.get("status") == "ok" and isinstance(r.get("timing"), dict)]

    def _avg(key: str) -> float | None:
        vals = [row[key] for row in t_rows if row.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    agg["timing"] = {
        "resolve_ms": _avg("resolve_ms"),
        "prompt_build_ms": _avg("prompt_build_ms"),
        "prefill_ms": _avg("prefill_ms"),
        "generation_ms": _avg("generation_ms"),
        "validate_ms": _avg("validate_ms"),
        "load_ms": _avg("load_ms"),
        "llm_total_ms": _avg("llm_total_ms"),
        "ttft_ms": _avg("ttft_ms"),
        "input_tokens": _avg("input_tokens"),
        "output_tokens": _avg("output_tokens"),
        "gen_tok_per_s": _avg("gen_tok_per_s"),
        "prefill_tok_per_s": _avg("prefill_tok_per_s"),
        "llm_calls": _avg("llm_calls"),
        "retries": _avg("retries"),
        "total_ms": _avg("total_ms"),
        "fallback_used_tasks": sum(1 for row in t_rows if row.get("fallback_used")),
        "thinking_detected_tasks": sum(1 for row in t_rows if row.get("thinking_detected")),
    }

    schema_ok = agg["schema_valid"]["count"] / agg["schema_valid"]["total"] if agg["schema_valid"]["total"] else 0
    cov_ok = (agg["citation_coverage_avg"] if agg["citation_coverage_avg"] is not None else 0) >= 0.95
    unsup_ok = (agg["unsupported_claim_rate_avg"] if agg["unsupported_claim_rate_avg"] is not None else 1) <= 0.05
    grip = not (agg["citation_invalid_tasks"] or failures)

    agg["gate"] = {
        "schema_valid_100": schema_ok >= 1.0,
        "citation_coverage_ge95": cov_ok,
        "unsupported_claim_le5": unsup_ok,
        "no_invalid_citation": grip,
        "overall_pass": bool(schema_ok >= 1.0 and cov_ok and unsup_ok and grip),
    }

    (out_dir / "synthesis_golden_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "synthesis_golden_failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"aggregate": agg, "gate": agg["gate"]}
    (out_dir / "synthesis_golden_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    report_conn.close()
    if cog_conn:
        cog_conn.close()
    return agg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None, help="KE_CONFIG 或 yaml 路径")
    ap.add_argument("--provider", default=None, choices=["mock", "ollama", "config"],
                    help="默认取 config 指定的 provider")
    ap.add_argument("--limit", type=int, default=None, help="随机抽样 N 条（seed=42 可复现）")
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parents[2] / "data"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    provider_name = args.provider if args.provider and args.provider != "config" else cfg.synthesis.provider
    tasks = _load_tasks(Path(args.outdir) / "synthesis_golden_tasks.jsonl", args.limit)
    print(f"[golden] tasks={len(tasks)} provider={provider_name} model={cfg.synthesis.model}")
    agg = run(cfg, tasks, provider_name, Path(args.outdir))
    print(f"[golden] ok={agg['tasks_ok']}/{agg['tasks_total']} "
          f"cov={agg['citation_coverage_avg']} unsup={agg['unsupported_claim_rate_avg']} "
          f"gate={agg['gate']}")
    tg = agg.get("timing") or {}
    if tg.get("total_ms"):
        print("[golden] timing avg: "
              f"total={tg['total_ms']}ms resolve={tg['resolve_ms']} prompt={tg['prompt_build_ms']} "
              f"prefill={tg['prefill_ms']}(TTFT) gen={tg['generation_ms']} "
              f"load={tg['load_ms']} llm_calls={tg['llm_calls']} retries={tg['retries']} "
              f"in_tok={tg['input_tokens']} out_tok={tg['output_tokens']} "
              f"gen_tok/s={tg['gen_tok_per_s']} think={tg.get('thinking_detected_tasks')}")
    print(f"[golden] results -> {Path(args.outdir)}/synthesis_golden_results.json")


if __name__ == "__main__":
    main()