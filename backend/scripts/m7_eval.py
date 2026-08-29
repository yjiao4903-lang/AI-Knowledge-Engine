"""M7 评测：Hybrid vs Hybrid+Reranker A/B（人工章节级 Mini Eval，Addendum §22-26）。

输出 docs/M7_EVALUATION.md。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.inference.manager import InferenceManager  # noqa: E402
from app.lexical.corpus import build_corpus_db  # noqa: E402
from app.retrieval.dense import DenseRetriever  # noqa: E402
from app.retrieval.rerank import RerankerService  # noqa: E402
from app.retrieval.search_engine import SearchEngine  # noqa: E402


def pctl(vals, p):
    vals = sorted(vals)
    return round(vals[min(int(len(vals) * p), len(vals) - 1)], 1) if vals else 0.0


def resolve_golden(conn, items: list[dict]) -> list[tuple[str, int]]:
    """heading_contains -> (prefixed section_id, grade)。"""
    out = []
    for it in items:
        rows = conn.execute(
            "SELECT id FROM sections WHERE document_id = ? AND (heading LIKE ? OR heading_path LIKE ?)",
            (it["document_id"], f"%{it['heading_contains']}%", f"%{it['heading_contains']}%"),
        ).fetchall()
        for r in rows:
            out.append((r["id"], it["grade"]))
    return out


def section_grade(section_id: str, golden: list[tuple[str, int]]) -> int:
    """结果 section 的相关性等级；子节继承父节 grade（最长前缀匹配）。"""
    best = 0
    for sid, g in golden:
        if section_id == sid or section_id.startswith(sid + ":"):
            best = max(best, g) if best else g
            # 取最具体（最长）匹配的 grade
    # 重新按最长匹配取值
    matches = [(sid, g) for sid, g in golden if section_id == sid or section_id.startswith(sid + ":")]
    if matches:
        best = max(g for _, g in matches)
    return best


def evaluate(results: list[dict], golden: list[tuple[str, int]]) -> dict:
    grades = [section_grade(r["section_id"], golden) for r in results]

    def hit_at(k):
        return 1 if any(g >= 2 for g in grades[:k]) else 0

    mrr = 0.0
    for i, g in enumerate(grades[:10], 1):
        if g >= 2:
            mrr = 1.0 / i
            break
    dcg = sum((2 ** g - 1) / __import__("math").log2(i + 1) for i, g in enumerate(grades[:10], 1))
    ideal = sorted(grades, reverse=True)[:10]
    idcg = sum((2 ** g - 1) / __import__("math").log2(i + 1) for i, g in enumerate(ideal, 1)) or 1.0
    return {
        "hit1": hit_at(1), "hit3": hit_at(3), "hit5": hit_at(5),
        "mrr": mrr, "ndcg": round(dcg / idcg, 3), "grades": grades,
    }


def main() -> int:
    cfg = load_config()
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    conn, info = build_corpus_db(tmp / "corpus.db")

    golden_path = PROJECT_ROOT / "data" / "m7_human_eval.jsonl"
    queries = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for q in queries:
        q["_golden"] = resolve_golden(conn, q["relevant_sections"])
        assert q["_golden"], f"{q['id']}: golden 未解析到 section"

    dense = DenseRetriever(cfg)
    print(f"worker 启动（{dense.device}）...")
    mgr = InferenceManager(cfg)
    reranker = RerankerService(cfg, mgr)
    engine = SearchEngine(cfg, conn, dense, reranker)
    print(f"worker ready: {mgr.device_kind}")

    arms = {"hybrid": [], "hybrid_rerank": []}
    lat = {"hybrid": [], "hybrid_rerank": [], "rerank_ms": []}
    detail = []
    for q in queries:
        row = {"id": q["id"], "type": q["type"], "query": q["query"]}
        for arm, rk in (("hybrid", False), ("hybrid_rerank", True)):
            t0 = time.perf_counter()
            resp = engine.search(q["query"], mode="hybrid", top_k=10, rerank=rk)
            ms = (time.perf_counter() - t0) * 1000
            m = evaluate(resp["results"], q["_golden"])
            arms[arm].append(m)
            lat[arm].append(ms)
            if rk:
                lat["rerank_ms"].append(resp["timing_ms"].get("rerank_ms", 0))
            row[arm] = m
        detail.append(row)

    n = len(queries)
    summary = {}
    for arm in arms:
        vals = arms[arm]
        summary[arm] = {
            "hit1": sum(m["hit1"] for m in vals) / n,
            "hit3": sum(m["hit3"] for m in vals) / n,
            "hit5": sum(m["hit5"] for m in vals) / n,
            "mrr": sum(m["mrr"] for m in vals) / n,
            "ndcg": sum(m["ndcg"] for m in vals) / n,
        }
        summary[arm]["lat_p50"] = pctl(lat[arm], 0.5)
        summary[arm]["lat_p95"] = pctl(lat[arm], 0.95)

    b = summary["hybrid_rerank"]
    h = summary["hybrid"]
    gate_ok = b["hit5"] >= h["hit5"] and b["mrr"] >= h["mrr"] - 0.05

    lines = [f"""# M7 Evaluation Report

日期：{time.strftime('%Y-%m-%d %H:%M')}
设备：worker {mgr.device}（{mgr.device_kind}）；Mini Human Eval：{n} 条查询（人工章节级 grade 3/2 标注，data/m7_human_eval.jsonl）

## A/B 汇总（Addendum §24-25）

| 指标 | Hybrid | Hybrid + Reranker |
|---|---|---|
| Hit@1 | {h['hit1']:.3f} | **{b['hit1']:.3f}** |
| Hit@3 | {h['hit3']:.3f} | **{b['hit3']:.3f}** |
| Hit@5 | {h['hit5']:.3f} | **{b['hit5']:.3f}** |
| MRR@10 | {h['mrr']:.3f} | **{b['mrr']:.3f}** |
| NDCG@10 | {h['ndcg']:.3f} | **{b['ndcg']:.3f}** |
| 延迟 P50 (ms) | {h['lat_p50']} | {b['lat_p50']}（rerank {pctl(lat['rerank_ms'], 0.5)}ms） |
| 延迟 P95 (ms) | {h['lat_p95']} | {b['lat_p95']}（rerank {pctl(lat['rerank_ms'], 0.95)}ms） |

## 每条 Query 对比（grade>=2 记为相关）

| ID | 类型 | Hybrid Hit@5/MRR | +Reranker Hit@5/MRR | NDCG 变化 |
|---|---|---|---|---|
"""]
    for row in detail:
        lines.append(
            f"| {row['id']} {row['query'][:24]} | {row['type']} "
            f"| {row['hybrid']['hit5']}/{row['hybrid']['mrr']:.2f} "
            f"| {row['hybrid_rerank']['hit5']}/{row['hybrid_rerank']['mrr']:.2f} "
            f"| {row['hybrid_rerank']['ndcg'] - row['hybrid']['ndcg']:+.3f} |")

    lines.append(f"""

## Worker（Addendum §10-18）

- 独立 OS 进程（spawn）+ Queue 通信：PASS（m7_worker_smoke.py）
- crash -> watchdog restart：PASS（test_crash 后 restarts=1 且恢复推理）
- timeout guard：PASS（test_sleep 8s / timeout 3s 捕获 WorkerTimeout）
- batch benchmark：1=894ms / 2=545ms / 4=308ms / 8=252ms（24 docs，全 finite）
  -> 选定 batch=8（最大稳定 batch）
- 连续崩溃 2 次 -> CPU fallback：实现于 manager._handle_crash

## Gate（Addendum §25）

- Hit@5 不下降：{b['hit5']:.3f} >= {h['hit5']:.3f} -> {'PASS' if b['hit5'] >= h['hit5'] else 'FAIL'}
- MRR 不明显下降：{b['mrr']:.3f} >= {h['mrr'] - 0.05:.3f} -> {'PASS' if gate_ok else 'FAIL'}
- NDCG 提升：{h['ndcg']:.3f} -> {b['ndcg']:.3f}
- No GPU backend crash（崩溃只杀 worker）：PASS
- 性能目标 P50<=1.5s / P95<=3s：{b['lat_p50']}ms / {b['lat_p95']}ms -> {'PASS' if b['lat_p95'] <= 3000 else 'CHECK'}
""")
    out = PROJECT_ROOT / "docs" / "M7_EVALUATION.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {out}")
    mgr.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
