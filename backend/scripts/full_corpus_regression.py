"""I0 全量语料 Golden Regression（主计划 §14 / HANDOFF_I0 §1.4）。

与 m9_eval.py 的区别：不在 fixtures 上重建临时语料，而是直接对**生产全量索引**
（catalog_full.db + kb_chunks_full_v1）运行 50 条 Golden Query 的 7-arm Ablation。
复用 m9_eval 的 resolve/metrics/bucket 逻辑。

Gate（Addendum §62）：hybrid_rerank Hit@5>=0.90 / MRR>=0.75 / NDCG>=0.80；
Exact/Semantic Hit@5 按类型聚合（阈值 0.95/0.85）。

用法：
  KE_CONFIG=config/config.full.yaml python backend/scripts/full_corpus_regression.py
输出：data/full_corpus_regression.json + data/full_corpus_regression_failures.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402

ARMS = ("terms", "trigram", "lexical", "dense", "hybrid", "hybrid_boost", "hybrid_rerank")


def main() -> int:
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    from app.inference.manager import InferenceManager
    from app.lexical.fts_search import LexicalSearcher
    from app.retrieval.dense import DenseRetriever
    from app.retrieval.rerank import RerankerService
    from app.retrieval.search_engine import SearchEngine
    from app.storage.sqlite import connect

    sys.path.insert(0, str(PROJECT_ROOT / "backend" / "scripts"))
    from m9_eval import (  # noqa: E402
        ARMS as M9_ARMS,
        bucket_failure,
        grade_chunk,
        metrics_for,
        pctl,
        resolve_golden,
    )

    conn = connect(cfg.sqlite.path)
    section_of = {r["id"]: r["section_id"] for r in conn.execute("SELECT id, section_id FROM chunks")}
    n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    n_chunks = len(section_of)
    print(f"corpus: docs={n_docs} chunks={n_chunks}")

    dense = DenseRetriever(cfg)
    mgr = InferenceManager(cfg)
    reranker = RerankerService(cfg, mgr)
    engine = SearchEngine(cfg, conn, dense, reranker)
    lexical = LexicalSearcher(conn)

    golden_path = PROJECT_ROOT / "data" / "golden_queries.jsonl"
    queries = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    unresolved = []
    for q in queries:
        q["_golden"] = resolve_golden(conn, q["relevant_sections"])
        if not q["_golden"]:
            unresolved.append(q["id"])
    if unresolved:
        print(f"WARNING: {len(unresolved)} 条 golden 未解析: {unresolved}")

    results_by_arm: dict[str, list] = {arm: [] for arm in ARMS}
    lat_by_arm: dict[str, list] = {arm: [] for arm in ARMS}
    per_type: dict[str, dict] = {}
    failures = []
    qrows = []

    for q in queries:
        if not q["_golden"]:
            continue
        golden = q["_golden"]
        qrow = {"id": q["id"], "type": q["type"], "query": q["query"], "arms": {}, "sources": {}}

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
            elif arm == "hybrid_boost":
                old = cfg.fusion.parent_boost_enabled
                cfg.fusion.parent_boost_enabled = True
                r = engine.search(q["query"], mode="hybrid", top_k=10)
                cfg.fusion.parent_boost_enabled = old
            elif arm == "hybrid_rerank":
                r = engine.search(q["query"], mode="hybrid", top_k=10, rerank=True)
            else:  # hybrid
                r = engine.search(q["query"], mode="hybrid", top_k=10)
            ids = [x["chunk_id"] for x in r["results"]]
            lat_by_arm[arm].append(r["timing_ms"]["total_ms"])
            return ids

        old_boost = cfg.fusion.parent_boost_enabled
        cfg.fusion.parent_boost_enabled = False
        ids_hybrid = run_arm("hybrid")
        cfg.fusion.parent_boost_enabled = old_boost
        m = metrics_for(ids_hybrid, golden, section_of)
        results_by_arm["hybrid"].append(m)
        qrow["arms"]["hybrid"] = m

        for arm in ("terms", "trigram", "lexical", "dense", "hybrid_boost", "hybrid_rerank"):
            ids = run_arm(arm)
            m = metrics_for(ids, golden, section_of)
            results_by_arm[arm].append(m)
            qrow["arms"][arm] = m

        hit5_best = max(qrow["arms"][a]["hit5"] for a in ARMS)
        if hit5_best == 0:
            failures.append({"id": q["id"], "bucket": bucket_failure(qrow), "query": q["query"]})
        elif qrow["arms"]["hybrid_rerank"]["hit5"] == 0:
            failures.append({"id": q["id"], "bucket": "BEST_ARM_FAIL",
                             "query": q["query"],
                             "detail": {a: qrow["arms"][a]["hit5"] for a in ARMS}})
        qrows.append(qrow)
        hr = qrow["arms"]["hybrid_rerank"]
        print(f"{q['id']} [{q['type']}] hit5={hr['hit5']} mrr={hr['mrr']} ndcg={hr['ndcg']}")

    def agg(arm):
        ms = results_by_arm[arm]
        n = len(ms)
        return {
            "n": n,
            "hit1": round(sum(m["hit1"] for m in ms) / n, 3) if n else 0.0,
            "hit3": round(sum(m["hit3"] for m in ms) / n, 3) if n else 0.0,
            "hit5": round(sum(m["hit5"] for m in ms) / n, 3) if n else 0.0,
            "recall5": round(sum(m["recall5"] for m in ms) / n, 3) if n else 0.0,
            "recall10": round(sum(m["recall10"] for m in ms) / n, 3) if n else 0.0,
            "mrr": round(sum(m["mrr"] for m in ms) / n, 3) if n else 0.0,
            "ndcg": round(sum(m["ndcg"] for m in ms) / n, 3) if n else 0.0,
            "p50_ms": pctl(lat_by_arm[arm], 0.5),
            "p95_ms": pctl(lat_by_arm[arm], 0.95),
        }

    summary = {arm: agg(arm) for arm in ARMS}

    # Exact / Semantic 按类型聚合（hybrid_rerank）
    for typ in sorted({q["type"] for q in queries if q.get("_golden")}):
        idx = [i for i, q in enumerate(queries) if q.get("_golden") and q["type"] == typ]
        per_type[typ] = {
            "n": len(idx),
            "hit5": round(sum(results_by_arm["hybrid_rerank"][i]["hit5"] for i in idx) / len(idx), 3),
            "mrr": round(sum(results_by_arm["hybrid_rerank"][i]["mrr"] for i in idx) / len(idx), 3),
        }

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": {"documents": n_docs, "chunks": n_chunks,
                   "catalog": cfg.sqlite.path,
                   "collections": [cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection]},
        "unresolved_golden": unresolved,
        "summary_by_arm": summary,
        "per_type_hybrid_rerank": per_type,
        "gate": {
            "hit5": {"value": summary["hybrid_rerank"]["hit5"], "threshold": 0.90},
            "mrr": {"value": summary["hybrid_rerank"]["mrr"], "threshold": 0.75},
            "ndcg": {"value": summary["hybrid_rerank"]["ndcg"], "threshold": 0.80},
            "exact_hit5": {"value": per_type.get("exact", {}).get("hit5", 0.0), "threshold": 0.95},
            "semantic_hit5": {"value": per_type.get("semantic", {}).get("hit5", 0.0), "threshold": 0.85},
        },
        "failures": failures,
    }
    out["gate_pass"] = all(v["value"] >= v["threshold"] for v in out["gate"].values())

    (PROJECT_ROOT / "data" / "full_corpus_regression.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (PROJECT_ROOT / "data" / "full_corpus_regression_failures.json").write_text(
        json.dumps({"failures": failures, "qrows": qrows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps({"summary": summary["hybrid_rerank"], "gate": out["gate"],
                      "gate_pass": out["gate_pass"]}, ensure_ascii=False, indent=2))
    mgr.shutdown()
    return 0 if out["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
