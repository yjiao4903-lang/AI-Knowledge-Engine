"""M9 Human-Labeled Golden Evaluation（Addendum §47-66）。

Ablation（Terms/Trigram/Lexical/Dense/Hybrid/Hybrid+Boost/Hybrid+Reranker）x
指标（Hit@1/3/5, Recall@5/10, MRR@10, NDCG@10）x 分类型 + 失败归因 + Quality Gate。

输出：docs/M9_GOLDEN_EVALUATION.md、data/m9_results.json、data/m9_failures.json
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.inference.manager import InferenceManager  # noqa: E402
from app.lexical.corpus import build_corpus_db  # noqa: E402
from app.lexical.fts_search import LexicalSearcher  # noqa: E402
from app.retrieval.dense import DenseRetriever  # noqa: E402
from app.retrieval.rerank import RerankerService  # noqa: E402
from app.retrieval.search_engine import SearchEngine  # noqa: E402

ARMS = ["terms", "trigram", "lexical", "dense", "hybrid", "hybrid_boost", "hybrid_rerank"]


def pctl(vals, p):
    vals = sorted(vals)
    return round(vals[min(int(len(vals) * p), len(vals) - 1)], 1) if vals else 0.0


def resolve_golden(conn, items):
    out = []
    for it in items:
        rows = conn.execute(
            "SELECT id FROM sections WHERE document_id = ? AND (heading LIKE ? OR heading_path LIKE ?)",
            (it["document_id"], f"%{it['heading_contains']}%", f"%{it['heading_contains']}%"),
        ).fetchall()
        for r in rows:
            out.append((r["id"], it["grade"]))
    return out


def grade_of(section_id: str, golden) -> int:
    matches = [(sid, g) for sid, g in golden
               if section_id == sid or section_id.startswith(sid + ":")]
    return max((g for _, g in matches), default=0)


def grade_chunk(chunk_id: str, golden, section_of: dict) -> int:
    sid = section_of.get(chunk_id)
    return grade_of(sid, golden) if sid else 0


def metrics_for(ranked_ids: list[str], golden, section_of: dict) -> dict:
    grades = [grade_chunk(cid, golden, section_of) for cid in ranked_ids[:10]]
    rel = [g >= 2 for g in grades]

    def hit(k):
        return 1 if any(rel[:k]) else 0

    def recall(k):
        total = sum(1 for _, g in golden if g >= 2)
        if total == 0:
            return 0.0
        found = set()
        for cid in ranked_ids[:k]:
            sid = section_of.get(cid)
            if sid and any(g >= 2 and (sid == s or sid.startswith(s + ":")) for s, g in golden):
                found.add(s for s, g in golden if g >= 2) if False else None
                for s, g in golden:
                    if g >= 2 and (sid == s or sid.startswith(s + ":")):
                        found.add(s)
        return len(found) / total

    mrr = 0.0
    for i, r in enumerate(rel, 1):
        if r:
            mrr = 1.0 / i
            break
    dcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(grades, 1))
    ideal = sorted(grades, reverse=True)
    idcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, 1)) or 1.0
    return {
        "hit1": hit(1), "hit3": hit(3), "hit5": hit(5),
        "recall5": round(recall(5), 3), "recall10": round(recall(10), 3),
        "mrr": round(mrr, 3), "ndcg": round(dcg / idcg, 3),
    }


def bucket_failure(qrow: dict) -> str:
    """失败归因（Addendum §65，简化规则）。"""
    src = qrow["sources"]
    if not any(src[s]["golden_top"] for s in ("dense", "terms", "trigram")):
        return "NO_RECALL"
    if qrow["arms"]["hybrid"]["hit5"] == 0 and (
            src["dense"]["golden_top10"] or src["terms"]["golden_top10"] or src["trigram"]["golden_top10"]):
        return "BAD_FUSION"
    if qrow["arms"]["hybrid"]["hit5"] and not qrow["arms"]["hybrid_rerank"]["hit5"]:
        return "BAD_RERANK"
    if qrow["arms"]["hybrid_boost"]["hit5"] and not qrow["arms"]["hybrid"]["hit5"]:
        return "BOOST_HURT"
    if qrow["arms"]["dense"]["hit5"] == 0:
        return "LOW_DENSE_RANK"
    return "LOW_LEXICAL_RANK"


def main() -> int:
    cfg = load_config()
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    conn, info = build_corpus_db(tmp / "corpus.db")
    section_of = {r["id"]: r["section_id"] for r in conn.execute("SELECT id, section_id FROM chunks")}

    # ---- 索引重建（10 docs）----
    dense = DenseRetriever(cfg)
    print(f"device={dense.device}")
    for col in (cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection):
        try:
            dense.store.client.delete_collection(col)
        except Exception:
            pass
    dense.ensure_collections()
    from app.chunking.semantic_chunker import SemanticChunker
    from app.core.config import ChunkingConfig
    from app.parser.markdown_parser import parse_markdown
    from app.retrieval.dense import build_section_records

    chunker = SemanticChunker(ChunkingConfig())
    t_idx0 = time.perf_counter()
    for name in info["documents"]:
        doc_id = name
        doc = parse_markdown((PROJECT_ROOT / "backend" / "tests" / "fixtures" / f"{name}_sample.md").read_text(encoding="utf-8"))
        chunks = chunker.chunk_document(doc, doc_id)
        meta = {"domain": doc.metadata.get("domain", ""), "completed_at": doc.metadata.get("completed_at", "")}
        dense.index_chunks(chunks, {doc_id: meta})
        dense.index_sections(build_section_records(doc, doc_id))
    idx_s = round(time.perf_counter() - t_idx0, 1)
    print(f"indexed 10 docs in {idx_s}s")

    mgr = InferenceManager(cfg)
    reranker = RerankerService(cfg, mgr)
    engine = SearchEngine(cfg, conn, dense, reranker)
    lexical = LexicalSearcher(conn)

    # ---- Golden ----
    golden_path = PROJECT_ROOT / "data" / "golden_queries.jsonl"
    queries = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for q in queries:
        q["_golden"] = resolve_golden(conn, q["relevant_sections"])
        assert q["_golden"], f"{q['id']} golden 未解析"

    # ---- Ablation 运行 ----
    results_by_arm: dict[str, list] = {arm: [] for arm in ARMS}
    lat_by_arm: dict[str, list] = {arm: [] for arm in ARMS}
    per_type: dict[str, dict] = {}
    failures = []

    for q in queries:
        golden = q["_golden"]
        qrow = {"id": q["id"], "type": q["type"], "query": q["query"], "arms": {}, "sources": {}}

        # 三路源（Top-K 候选，用于 recall 溯源与归因）
        dh, _ = dense.search(q["query"], k=50)
        th = lexical.search_terms(q["query"], k=50)
        gh = lexical.search_trigram(q["query"], k=30)
        src_ids = {
            "dense": [h["payload"]["chunk_id"] for h in dh],
            "terms": [h.chunk_id for h in th],
            "trigram": [h.chunk_id for h in gh],
        }
        for s, ids in src_ids.items():
            qrow["sources"][s] = {
                "golden_top": [i for i in ids if grade_chunk(i, golden, section_of) >= 2][:1],
                "golden_top10": [i for i in ids[:10] if grade_chunk(i, golden, section_of) >= 2][:1],
            }

        def run_arm(arm) -> list[str]:
            if arm == "terms":
                return src_ids["terms"][:10]
            if arm == "trigram":
                return src_ids["trigram"][:10]
            if arm == "lexical":
                r = engine.search(q["query"], mode="lexical", top_k=10)
            elif arm == "dense":
                r = engine.search(q["query"], mode="dense", top_k=10)
            elif arm == "hybrid":
                r = engine.search(q["query"], mode="hybrid", top_k=10)
            elif arm == "hybrid_boost":
                old = cfg.fusion.parent_boost_enabled
                cfg.fusion.parent_boost_enabled = True
                r = engine.search(q["query"], mode="hybrid", top_k=10)
                cfg.fusion.parent_boost_enabled = old
            elif arm == "hybrid_rerank":
                r = engine.search(q["query"], mode="hybrid", top_k=10, rerank=True)
            ids = [x["chunk_id"] for x in r["results"]]
            lat_by_arm[arm].append(r["timing_ms"]["total_ms"])
            return ids

        # hybrid（无 boost）需要临时关闭 boost
        old_boost = cfg.fusion.parent_boost_enabled
        cfg.fusion.parent_boost_enabled = False
        ids_hybrid = run_arm("hybrid")
        cfg.fusion.parent_boost_enabled = old_boost
        results_by_arm["hybrid"].append(metrics_for(ids_hybrid, golden, section_of))
        qrow["arms"]["hybrid"] = metrics_for(ids_hybrid, golden, section_of)

        for arm in ("terms", "trigram", "lexical", "dense", "hybrid_boost", "hybrid_rerank"):
            ids = run_arm(arm)
            m = metrics_for(ids, golden, section_of)
            results_by_arm[arm].append(m)
            qrow["arms"][arm] = m

        hit5_best = max(qrow["arms"][a]["hit5"] for a in ARMS)
        if hit5_best == 0:
            qrow["bucket"] = bucket_failure(qrow)
        else:
            # 找出仍失败的 arm（多样性归因）
            failed = [a for a in ("dense", "lexical", "hybrid", "hybrid_rerank") if qrow["arms"][a]["hit5"] == 0]
            qrow["bucket"] = "OK" if not failed else "PARTIAL:" + ",".join(failed)
        failures.append(qrow)

        t = q["type"]
        per_type.setdefault(t, {arm: [] for arm in ARMS})
        for arm in ARMS:
            per_type[t][arm].append(results_by_arm[arm][-1])

    n = len(queries)
    summary = {}
    for arm in ARMS:
        ms = results_by_arm[arm]
        summary[arm] = {
            "hit1": round(sum(m["hit1"] for m in ms) / n, 3),
            "hit3": round(sum(m["hit3"] for m in ms) / n, 3),
            "hit5": round(sum(m["hit5"] for m in ms) / n, 3),
            "recall5": round(sum(m["recall5"] for m in ms) / n, 3),
            "recall10": round(sum(m["recall10"] for m in ms) / n, 3),
            "mrr": round(sum(m["mrr"] for m in ms) / n, 3),
            "ndcg": round(sum(m["ndcg"] for m in ms) / n, 3),
            "p50": pctl(lat_by_arm[arm], 0.5), "p95": pctl(lat_by_arm[arm], 0.95),
        }

    type_summary = {}
    for t, arms in per_type.items():
        cnt = len(arms["hybrid"])
        type_summary[t] = {
            "n": cnt,
            "hit5": {arm: round(sum(m["hit5"] for m in v) / cnt, 3) for arm, v in arms.items()},
            "mrr": {arm: round(sum(m["mrr"] for m in v) / cnt, 3) for arm, v in arms.items()},
        }

    s = summary
    gate = {
        "hit5": s["hybrid_rerank"]["hit5"] >= 0.90 or s["hybrid_boost"]["hit5"] >= 0.90 or s["hybrid"]["hit5"] >= 0.90,
        "mrr": max(s[a]["mrr"] for a in ("hybrid", "hybrid_boost", "hybrid_rerank")) >= 0.75,
        "ndcg": max(s[a]["ndcg"] for a in ("hybrid", "hybrid_boost", "hybrid_rerank")) >= 0.80,
    }
    ex_types = [type_summary[t] for t in type_summary if t == "exact"]
    sem_types = [type_summary[t] for t in type_summary if t == "semantic"]
    gate["exact_hit5"] = ex_types and max(v["hit5"]["hybrid_rerank"] for v in ex_types) >= 0.95
    gate["semantic_hit5"] = sem_types and max(v["hit5"]["hybrid_rerank"] for v in sem_types) >= 0.85

    best_arm = max(("hybrid", "hybrid_boost", "hybrid_rerank"), key=lambda a: summary[a]["ndcg"])

    out_json = {"n_queries": n, "corpus": info, "summary": summary, "per_type": type_summary,
                "gate": gate, "best_arm": best_arm, "index_seconds": idx_s}
    (PROJECT_ROOT / "data" / "m9_results.json").write_text(
        json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (PROJECT_ROOT / "data" / "m9_failures.json").write_text(
        json.dumps([f for f in failures if f["bucket"] != "OK"], ensure_ascii=False, indent=2),
        encoding="utf-8")

    # ---- Markdown 报告 ----
    lines = [f"""# M9 Golden Evaluation Report（Human-Labeled）

日期：{time.strftime('%Y-%m-%d %H:%M')}
语料：10 篇报告 / {info['total_chunks']} chunks / {info['documents'].__len__()} docs（索引 {idx_s}s）
Golden Set：{n} 条人工章节级标注（grade 3/2，data/golden_queries.jsonl）

## Ablation 汇总（Addendum §57）

| Arm | Hit@1 | Hit@3 | Hit@5 | Recall@5 | Recall@10 | MRR@10 | NDCG@10 | P50/P95 ms |
|---|---|---|---|---|---|---|---|---|"""]
    for arm in ARMS:
        v = summary[arm]
        lines.append(
            f"| {arm} | {v['hit1']} | {v['hit3']} | {v['hit5']} | {v['recall5']} | "
            f"{v['recall10']} | {v['mrr']} | {v['ndcg']} | {v['p50']}/{v['p95']} |")

    lines.append("\n## 分类型 Hit@5 / MRR（Addendum §58）\n")
    lines.append("| 类型 | n | 最优 Arm | Hit@5（各 arm） | MRR（各 arm） |")
    lines.append("|---|---|---|---|---|")
    for t, ts in sorted(type_summary.items()):
        best = max(ts["hit5"], key=ts["hit5"].get)
        lines.append(
            f"| {t} | {ts['n']} | {best} | {ts['hit5']} | {ts['mrr']} |")

    ok_buckets = sum(1 for f in failures if f["bucket"] == "OK")
    buckets = {}
    for f in failures:
        if f["bucket"] != "OK":
            buckets[f["bucket"]] = buckets.get(f["bucket"], 0) + 1
    lines.append(f"""

## 失败归因（Addendum §64-65）

- 完全通过（全部 arm Hit@5=1）：{ok_buckets}/{n}
- 失败桶分布：{json.dumps(buckets, ensure_ascii=False)}
- 明细见 data/m9_failures.json（含各路 golden 命中溯源）

## Retrieval Quality Gate（Addendum §62）

| 条件 | 阈值 | 实际 | 判定 |
|---|---|---|---|
| Hit@5 | >= 0.90 | {max(s[a]['hit5'] for a in ('hybrid','hybrid_boost','hybrid_rerank'))} | {'PASS' if gate['hit5'] else 'FAIL'} |
| MRR@10 | >= 0.75 | {max(s[a]['mrr'] for a in ('hybrid','hybrid_boost','hybrid_rerank'))} | {'PASS' if gate['mrr'] else 'FAIL'} |
| NDCG@10 | >= 0.80 | {max(s[a]['ndcg'] for a in ('hybrid','hybrid_boost','hybrid_rerank'))} | {'PASS' if gate['ndcg'] else 'FAIL'} |
| Exact Hit@5 | >= 0.95 | {type_summary.get('exact', {}).get('hit5', {}).get('hybrid_rerank', '-')} | {'PASS' if gate['exact_hit5'] else 'FAIL'} |
| Semantic Hit@5 | >= 0.85 | {type_summary.get('semantic', {}).get('hit5', {}).get('hybrid_rerank', '-')} | {'PASS' if gate['semantic_hit5'] else 'FAIL'} |

**最优 Arm：{best_arm}**

## Reranker 最终判断（Addendum §61）

- Hybrid vs Hybrid+Reranker：Hit@5 {s['hybrid']['hit5']} -> {s['hybrid_rerank']['hit5']}，
  MRR {s['hybrid']['mrr']} -> {s['hybrid_rerank']['mrr']}，NDCG {s['hybrid']['ndcg']} -> {s['hybrid_rerank']['ndcg']}
- 结论：{'Reranker 默认 ON' if s['hybrid_rerank']['ndcg'] >= s['hybrid']['ndcg'] else 'Reranker 默认 OFF'}
""")
    out_md = PROJECT_ROOT / "docs" / "M9_GOLDEN_EVALUATION.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {out_md}")
    mgr.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
