# -*- coding: utf-8 -*-
"""P8-BENCH-02：pooled relevance judging 与 false-negative 审计。

对冻结题集，用 4 个**冻结检索视图**（lexical / dense / hybrid / hybrid+rerank）各取 top-20
构建候选池；对池中每个 chunk 用题目 rubric 判定相关度；把"池中相关但未标注"的 chunk 记为
false-negative 候选并在 freeze 前补入 gold。**不修改任何检索参数**，仅用输出构建评测池。

用法:
  python docs/p8_review/scripts/p8_bench_pool.py --questions <dev.jsonl> --split development \
      --out <audit.json> --corrected <dev_corrected.jsonl>
  python docs/p8_review/scripts/p8_bench_pool.py --questions <sealed holdout.jsonl> --split holdout \
      --out <holdout_audit.json> --corrected <sealed holdout corrected.jsonl>
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CATALOG = REPO / "data" / "catalog_full.db"
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))


def ro():
    c = sqlite3.connect(f"file:{CATALOG.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def grade_chunk(rubric: dict, blob: str) -> int:
    req = [t for t in rubric.get("req", []) if t]
    if not req or not all(t.lower() in blob for t in req):
        return 0
    for p in rubric.get("requires_any", []):
        if not re.search(p, blob, re.I):
            return 0
    return 3


def load_questions(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--corrected")
    ap.add_argument("--topn", type=int, default=20)
    a = ap.parse_args()

    from app.core.config import load_config
    from app.inference.manager import InferenceManager
    from app.lexical.fts_search import LexicalSearcher
    from app.retrieval.dense import DenseRetriever
    from app.retrieval.fusion import weighted_rrf
    from app.retrieval.rerank import RerankerService

    cfg = load_config()
    conn = ro()
    qs = load_questions(Path(a.questions))
    # 该 split 允许作为 gold 的文档集（与生成器同一确定性切分）——禁止跨 split 泄漏
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import p8_bench_build as base
    dev_map, hold_map = base.make_splits(base.load_corpus(conn))
    active = dev_map if a.split == "development" else hold_map
    allowed = {d["id"] for ds in active.values() for d in ds}
    dense = DenseRetriever(cfg)
    mgr = InferenceManager(cfg)
    reranker = RerankerService(cfg, mgr)
    lexical = LexicalSearcher(conn)

    def fuse(lists):
        fused = weighted_rrf(lists, rrf_k=cfg.fusion.rrf_k, weights={
            "dense": cfg.fusion.dense_weight, "terms": cfg.fusion.terms_weight,
            "trigram": cfg.fusion.trigram_weight})
        score_map = {cid: sc for cid, sc, _ in fused}
        order, seen = [], set()
        for cid in lists.get("dense", []) + lists.get("terms", []) + lists.get("trigram", []) \
                + [c for c, _, _ in fused]:
            if cid not in seen:
                seen.add(cid); order.append(cid)
        return sorted(order, key=lambda c: score_map.get(c, 0.0), reverse=True), score_map

    def rows_for(ids):
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        return {r["id"]: r for r in conn.execute(
            f"SELECT id, document_id, plain_text, heading_path, section_id FROM chunks WHERE id IN ({marks})",
            tuple(ids))}

    audit = {"split": a.split, "questions": a.questions, "topn": a.topn, "per_query": [],
             "fn_corrections": 0, "pooled_relevant_total": 0}
    corrected = []
    t0 = time.perf_counter()
    for n, q in enumerate(qs, 1):
        views = {}
        dh, _ = dense.search(q["query"], k=a.topn, filters=None,
                             collection=cfg.qdrant.chunks_collection)
        views["dense"] = [h["payload"]["chunk_id"] for h in dh][:a.topn]
        views["lexical"] = list(dict.fromkeys(
            [h.chunk_id for h in lexical.search_terms(q["query"], k=a.topn, filters=None)]
            + [h.chunk_id for h in lexical.search_trigram(q["query"], k=a.topn, filters=None)]))[:a.topn]
        lists = {"dense": views["dense"],
                 "terms": [h.chunk_id for h in lexical.search_terms(q["query"], k=a.topn, filters=None)],
                 "trigram": [h.chunk_id for h in lexical.search_trigram(q["query"], k=a.topn, filters=None)]}
        fused_all, _ = fuse(lists)
        views["hybrid"] = fused_all[:a.topn]
        fused_top = fused_all[:cfg.retrieval.fused_k]
        rr = rows_for(fused_top)
        cands = [{"chunk_id": c, "title": rr[c]["document_id"], "heading_path": rr[c]["heading_path"],
                  "content_type": "", "evidence_level": "", "plain_text": rr[c]["plain_text"]}
                 for c in fused_top if c in rr]
        reranked = reranker.rerank(q["query"], cands) if cands else []
        views["hybrid_rerank"] = [x["chunk_id"] for x in reranked][:a.topn]

        pool = list(dict.fromkeys(sum(views.values(), [])))
        pool_rows = rows_for(pool)
        gold_ids = [c["chunk_id"] for c in q["gold"]["chunks"]]
        gold_rows = rows_for(gold_ids)
        gold = {c["chunk_id"]: c["grade"] for c in q["gold"]["chunks"]
                if gold_rows.get(c["chunk_id"]) and gold_rows[c["chunk_id"]]["document_id"] in allowed}
        rubric = q.get("judging", {}).get("rubric", {"req": [], "requires_any": []})
        judged, fn = {}, []
        cross_split = 0
        for cid in pool:
            r = pool_rows.get(cid)
            if not r:
                continue
            if r["document_id"] not in allowed:
                cross_split += 1
                continue  # 非本 split 文档：不作为 gold，避免跨 split 泄漏
            blob = ((r["plain_text"] or "") + "\n" + (r["heading_path"] or "")).lower()
            g = grade_chunk(rubric, blob)
            judged[cid] = g
            if g >= 2 and cid not in gold:
                fn.append({"chunk_id": cid, "grade": g})
        for x in fn:
            gold[x["chunk_id"]] = x["grade"]
        if fn:
            audit["fn_corrections"] += len(fn)
        rel_in_pool = sum(1 for g in judged.values() if g >= 2)
        audit["pooled_relevant_total"] += rel_in_pool
        audit["per_query"].append({
            "id": q["id"], "family": q["query_type"], "tier": q["corpus_tier"],
            "query": q["query"], "pool_size": len(pool),
            "pool_by_view": {k: len(v) for k, v in views.items()},
            "pooled_relevant": rel_in_pool,
            "pooled_grade3": sum(1 for g in judged.values() if g == 3),
            "gold_size": len(gold), "gold_g3": sum(1 for g in gold.values() if g >= 3),
            "fn_corrections": len(fn), "fn": fn[:10],
            "cross_split_ignored": cross_split,
        })
        q["gold"]["chunks"] = [{"chunk_id": c, "grade": g} for c, g in sorted(gold.items())]
        q["judging"]["pooled"] = True
        q["judging"]["fn_audit"] = True
        q["judging"]["pool_size"] = len(pool)
        q["judging"]["pooled_relevant"] = rel_in_pool
        corrected.append(q)
        if n % 10 == 0 or n == len(qs):
            print(f"  [{n}/{len(qs)}] {q['id']} pool={len(pool)} rel={rel_in_pool} fn={len(fn)}", flush=True)

    pool_sizes = [x["pool_size"] for x in audit["per_query"]]
    rels = [x["pooled_relevant"] for x in audit["per_query"]]
    g3 = [x["pooled_grade3"] for x in audit["per_query"]]
    audit["summary"] = {
        "n": len(qs), "elapsed_s": round(time.perf_counter() - t0, 1),
        "pool_size_median": sorted(pool_sizes)[len(pool_sizes) // 2],
        "pool_size_max": max(pool_sizes) if pool_sizes else 0,
        "pooled_relevant_median": sorted(rels)[len(rels) // 2] if rels else 0,
        "pooled_grade3_median": sorted(g3)[len(g3) // 2] if g3 else 0,
        "queries_with_no_pooled_grade3": sum(1 for x in g3 if x == 0),
        "queries_with_gold_grade3_after_split_scope": sum(1 for x in audit["per_query"] if x["gold_g3"] > 0),
        "fn_corrections": audit["fn_corrections"],
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print("audit:", json.dumps(audit["summary"], ensure_ascii=False))
    if a.corrected:
        with open(a.corrected, "w", encoding="utf-8") as f:
            for q in corrected:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")
        print("wrote corrected", a.corrected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
