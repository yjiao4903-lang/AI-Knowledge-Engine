# -*- coding: utf-8 -*-
"""P8-BENCH-02：四个**冻结检索视图**的单一实现（lexical / dense / hybrid / hybrid+rerank）。

`p8_bench_pool.py`（自动预标注 + 建池）与 `p8_bench_adjudicate.py`（盲化人审包）共用本模块，
以保证"建池"和"人工判定包"看到的是**完全相同**的候选集合与顺序。

**本模块不修改任何检索参数。** 只复现既有检索链路（weighted_rrf 融合 + 稳定排序），
不做 parent boost —— 与 `p8_bench_pool.py` 此前内联的实现逐行等价。

冻结视图定义（见 Issue #39 "Relevance judging" 一节）：
  1. `lexical`       — terms FTS + trigram FTS 去重；
  2. `dense`         — 向量 top-k；
  3. `hybrid`        — weighted_rrf 融合全序（未截断名次）；
  4. `hybrid_rerank` — 融合 top-`fused_k` 经 reranker 重排后的顺序。

用法：
    from p8_bench_views import FrozenViews, open_catalog, rows_for
    fv = FrozenViews()
    views, fused_all = fv.views("查询文本", topn=50)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CATALOG = REPO / "data" / "catalog_full.db"
BACKEND = REPO / "backend"

VIEW_NAMES = ("dense", "lexical", "hybrid", "hybrid_rerank")


def ensure_backend_on_path() -> None:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))


def open_catalog(path: str | Path | None = None):
    p = Path(path) if path else CATALOG
    c = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def fuse(lists: dict, cfg):
    """复现 `p8_bench_pool.py` 的候选构造：weighted_rrf 打分 + 插入序稳定排序（无 parent boost）。

    返回 (全序 chunk_id 列表, score_map)。
    """
    from app.retrieval.fusion import weighted_rrf
    fused = weighted_rrf(lists, rrf_k=cfg.fusion.rrf_k, weights={
        "dense": cfg.fusion.dense_weight,
        "terms": cfg.fusion.terms_weight,
        "trigram": cfg.fusion.trigram_weight})
    score_map = {cid: sc for cid, sc, _ in fused}
    order, seen = [], set()
    for cid in lists.get("dense", []) + lists.get("terms", []) + lists.get("trigram", []) \
            + [c for c, _, _ in fused]:
        if cid not in seen:
            seen.add(cid)
            order.append(cid)
    return sorted(order, key=lambda c: score_map.get(c, 0.0), reverse=True), score_map


def rows_for(conn, ids):
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    return {r["id"]: r for r in conn.execute(
        f"SELECT id, document_id, plain_text, heading_path, section_id "
        f"FROM chunks WHERE id IN ({marks})", tuple(ids))}


class FrozenViews:
    """四个冻结视图。模型只加载一次，可对多条 query 复用。"""

    def __init__(self, cfg=None, conn=None):
        ensure_backend_on_path()
        from app.core.config import load_config
        from app.inference.manager import InferenceManager
        from app.lexical.fts_search import LexicalSearcher
        from app.retrieval.dense import DenseRetriever
        from app.retrieval.rerank import RerankerService

        self.cfg = cfg or load_config()
        self.conn = conn or open_catalog()
        self.dense = DenseRetriever(self.cfg)
        self.lexical = LexicalSearcher(self.conn)
        self.mgr = InferenceManager(self.cfg)
        self.reranker = RerankerService(self.cfg, self.mgr)

    def views(self, query: str, topn: int = 50):
        """返回 ({view_name: [chunk_id...]}, fused_all)。每个视图各取 topn。"""
        cfg = self.cfg
        dh, _ = self.dense.search(query, k=topn, filters=None,
                                  collection=cfg.qdrant.chunks_collection)
        dense_ids = [h["payload"]["chunk_id"] for h in dh][:topn]

        terms = [h.chunk_id for h in self.lexical.search_terms(query, k=topn, filters=None)]
        trigram = [h.chunk_id for h in self.lexical.search_trigram(query, k=topn, filters=None)]
        lexical_ids = list(dict.fromkeys(terms + trigram))[:topn]

        fused_all, _ = fuse({"dense": dense_ids, "terms": terms, "trigram": trigram}, cfg)
        hybrid_ids = fused_all[:topn]

        fused_top = fused_all[:cfg.retrieval.fused_k]
        rr = rows_for(self.conn, fused_top)
        cands = [{"chunk_id": c, "title": rr[c]["document_id"], "heading_path": rr[c]["heading_path"],
                  "content_type": "", "evidence_level": "", "plain_text": rr[c]["plain_text"]}
                 for c in fused_top if c in rr]
        reranked = self.reranker.rerank(query, cands) if cands else []
        rerank_ids = [x["chunk_id"] for x in reranked][:topn]

        return {"dense": dense_ids, "lexical": lexical_ids,
                "hybrid": hybrid_ids, "hybrid_rerank": rerank_ids}, fused_all

    def close(self) -> None:
        try:
            self.mgr.close()
        except Exception:
            pass
