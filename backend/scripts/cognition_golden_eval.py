"""I7 P0-4：Cognition Golden Mini Evaluation。

读 data/cognition_golden_queries.jsonl（人工标注，>=20 条），用真实 cognition
只读语义检索（独立 catalog_cognition.db + kb_cognition_chunks_v1）评测：

    输出 Hit@1 / Hit@3 / Hit@5 / MRR@10 / NDCG@10（binary relevance）
    按类型分组 + 全局 + 失败明细

用法（GPU 串行，只读检索，不写认知）：
  KE_CONFIG=config/config.prod.yaml .venv\\Scripts\\python.exe backend/scripts/cognition_golden_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402


def main() -> int:
    cfg = load_config()
    qpath = PROJECT_ROOT / "data" / "cognition_golden_queries.jsonl"
    if not qpath.exists():
        print(f"缺标注文件: {qpath}")
        return 2

    # ---- 构建真实 cognition 检索（独立 catalog + collection，只读） ----
    from app.retrieval.dense import DenseRetriever
    from app.retrieval.search_engine import SearchEngine
    from app.storage.sqlite import connect

    conn = connect(cfg.cognition.catalog_path, read_only=True)
    dense = DenseRetriever(cfg)
    engine = SearchEngine(
        cfg, conn, dense,
        chunks_collection=cfg.cognition.chunks_collection,
        section_boost_enabled=False,
    )
    print(f"device={dense.device} collection={cfg.cognition.chunks_collection}")

    queries = [json.loads(l) for l in qpath.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"queries={len(queries)}")

    import math

    def ndcg10(rel: list[bool], n_rel: int) -> float:
        # binary relevance；position 权重 1/log2(pos+1)，IDCG = 前 n_rel 位全相关（理想排序）
        dcg = sum((1.0 / math.log2(i + 2)) for i, r in enumerate(rel[:10]) if r)
        k = min(n_rel, 10)
        idcg = sum(1.0 / math.log2(pos + 1) for pos in range(1, k + 1))
        return dcg / idcg if idcg else 0.0

    per_type: dict[str, list] = {}
    failures: list[dict] = []
    global_stats = {"hit1": 0, "hit3": 0, "hit5": 0, "mrr": 0.0, "ndcg": 0.0}
    n = 0
    for q in queries:
        targets = q["targets"]
        # 库内相关对象数 R（匹配任一 target 的 doc 数，上限 10），用于 NDCG IDCG
        like = " OR ".join(["id LIKE ?"] * len(targets))
        rel_rows = conn.execute(
            f"SELECT id FROM documents WHERE {like}",
            [f"%{t}%" for t in targets],
        ).fetchall()
        n_rel = min(len(rel_rows), 10)

        resp = engine.search(q["query"], mode="hybrid", top_k=10, rerank=False)
        results = resp["results"] if resp else []
        doc_ids = [r["document_id"] for r in results if r]
        # NDCG 按唯一文档计（同一 doc 多 chunk 不重复增益）
        seen: set = set()
        uniq: list[str] = []
        for did in doc_ids[:10]:
            if did not in seen:
                seen.add(did)
                uniq.append(did)
        rel_ndcg = [any(t in did for t in targets) for did in uniq]
        first_hit = next((i + 1 for i, did in enumerate(doc_ids[:10])
                          if any(t in did for t in targets)), None)
        h1 = first_hit is not None and first_hit == 1
        h3 = first_hit is not None and first_hit <= 3
        h5 = first_hit is not None and first_hit <= 5
        global_stats["hit1"] += h1
        global_stats["hit3"] += h3
        global_stats["hit5"] += h5
        global_stats["mrr"] += (1.0 / first_hit if first_hit else 0.0)
        global_stats["ndcg"] += ndcg10(rel_ndcg, n_rel)
        per_type.setdefault(q["type"], []).append(
            {"hit@1": h1, "hit@3": h3, "hit@5": h5,
             "rr": 1.0 / first_hit if first_hit else 0.0,
             "ndcg": ndcg10(rel_ndcg, n_rel)})
        if not h5:
            failures.append({"id": q["id"], "type": q["type"], "query": q["query"],
                             "targets": targets, "n_rel": n_rel, "top5": doc_ids[:5]})
        n += 1

    total = float(n)
    out = {
        "total_queries": n,
        "hit_at_1": global_stats["hit1"] / total,
        "hit_at_3": global_stats["hit3"] / total,
        "hit_at_5": global_stats["hit5"] / total,
        "mrr_10": global_stats["mrr"] / total,
        "ndcg_10": global_stats["ndcg"] / total,
        "by_type": {
            k: {"count": len(v),
                "hit_at_5": sum(x["hit@5"] for x in v) / len(v),
                "mrr_10": sum(x["rr"] for x in v) / len(v),
                "ndcg_10": sum(x["ndcg"] for x in v) / len(v)}
            for k, v in per_type.items()
        },
        "failures": failures,
    }
    (PROJECT_ROOT / "data" / "cognition_golden_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (PROJECT_ROOT / "data" / "cognition_golden_failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==== Cognition Golden Evaluation ====")
    print(f"total_queries = {n}")
    print(f"Hit@1 = {out['hit_at_1']:.3f}")
    print(f"Hit@3 = {out['hit_at_3']:.3f}")
    print(f"Hit@5 = {out['hit_at_5']:.3f}")
    print(f"MRR@10 = {out['mrr_10']:.3f}")
    print(f"NDCG@10 = {out['ndcg_10']:.3f}")
    print("by_type:")
    for k, v in out["by_type"].items():
        print(f"  {k:12s} n={v['count']:2d}  Hit@5={v['hit_at_5']:.3f}  "
              f"MRR@10={v['mrr_10']:.3f}  NDCG@10={v['ndcg_10']:.3f}")
    print(f"failures (Hit@5 miss) = {len(failures)}")
    for f in failures:
        print(f"  [{f['type']}] {f['id']} {f['query']} -> top5={f['top5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())