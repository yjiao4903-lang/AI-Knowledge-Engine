"""Hybrid Search Engine（M6，spec §32/§34-41 + Addendum §33-41）。

三路候选（Dense 50 / Terms 50 / Trigram 30）-> Weighted RRF -> 去重 ->
Section Parent Boost（轻量 prior，非硬过滤）-> Metadata 过滤 -> Top-K。

每条候选记录 dense_rank/terms_rank/trigram_rank/rrf/section_boost，全部可解释。
搜索模式：dense / lexical / hybrid。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import sqlite3

from app.core.config import Config
from app.lexical.fts_search import LexicalSearcher
from app.retrieval.dense import DenseRetriever
from app.retrieval.fusion import weighted_rrf

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    chunk_id: str
    document_id: str = ""
    section_id: str = ""
    ranks: dict[str, int | None] = field(default_factory=dict)  # dense/terms/trigram
    rrf_score: float = 0.0
    section_boost: float = 1.0
    final_score: float = 0.0

    @property
    def merged_section_id(self) -> str:
        return self.section_id


class SearchEngine:
    def __init__(self, cfg: Config, conn: sqlite3.Connection, dense: DenseRetriever,
                 reranker: "RerankerService | None" = None) -> None:
        self.cfg = cfg
        self.conn = conn
        self.dense = dense
        self.lexical = LexicalSearcher(conn)
        self.reranker = reranker

    # ---- 主入口 ----
    def search(
        self,
        query: str,
        *,
        mode: str = "hybrid",  # dense | lexical | hybrid
        top_k: int | None = None,
        filters: dict | None = None,
        debug: bool = False,
        rerank: bool = False,
    ) -> dict[str, Any]:
        cfg = self.cfg
        t_start = time.perf_counter()
        timing: dict[str, float] = {k: 0.0 for k in
                                    ("embed_ms", "dense_ms", "terms_ms", "trigram_ms",
                                     "fusion_ms", "section_ms", "filter_ms", "total_ms")}

        candidates: dict[str, Candidate] = {}
        ranked_lists: dict[str, list[str]] = {}
        debug_trace: dict[str, Any] = {"query": query, "mode": mode, "sources": {}}

        # 1) Dense
        if mode in ("hybrid", "dense"):
            t0 = time.perf_counter()
            dense_hits, embed_ms = self.dense.search(
                query, k=cfg.retrieval.dense_k, filters=filters)
            timing["embed_ms"] = embed_ms
            timing["dense_ms"] = round((time.perf_counter() - t0) * 1000 - embed_ms, 2)
            ranked_lists["dense"] = [h["payload"]["chunk_id"] for h in dense_hits]
            dense_scores = {h["payload"]["chunk_id"]: h for h in dense_hits}
            for cid, h in dense_scores.items():
                candidates.setdefault(cid, Candidate(chunk_id=cid)).ranks["dense"] = None
            for rank, cid in enumerate(ranked_lists["dense"], 1):
                candidates[cid].ranks["dense"] = rank
            if debug:
                debug_trace["sources"]["dense"] = ranked_lists["dense"][:10]

        # 2) Lexical（terms + trigram）
        if mode in ("hybrid", "lexical"):
            t0 = time.perf_counter()
            terms_hits = self.lexical.search_terms(query, k=cfg.retrieval.fts_terms_k)
            timing["terms_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            t0 = time.perf_counter()
            trigram_hits = self.lexical.search_trigram(query, k=cfg.retrieval.fts_trigram_k)
            timing["trigram_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            ranked_lists["terms"] = [h.chunk_id for h in terms_hits]
            ranked_lists["trigram"] = [h.chunk_id for h in trigram_hits]
            for rank, cid in enumerate(ranked_lists["terms"], 1):
                candidates.setdefault(cid, Candidate(chunk_id=cid)).ranks["terms"] = rank
            for rank, cid in enumerate(ranked_lists["trigram"], 1):
                candidates.setdefault(cid, Candidate(chunk_id=cid)).ranks["trigram"] = rank
            if debug:
                debug_trace["sources"]["terms"] = ranked_lists["terms"][:10]
                debug_trace["sources"]["trigram"] = ranked_lists["trigram"][:10]

        # 3) Weighted RRF 融合（dense-only / lexical-only 模式也用 RRF 统一排序）
        t0 = time.perf_counter()
        fused = weighted_rrf(
            ranked_lists,
            rrf_k=cfg.fusion.rrf_k,
            weights={
                "dense": cfg.fusion.dense_weight,
                "terms": cfg.fusion.terms_weight,
                "trigram": cfg.fusion.trigram_weight,
            },
        )
        for cid, score, ranks in fused:
            c = candidates[cid]
            c.rrf_score = score
            c.ranks = {**c.ranks, **{k: v for k, v in ranks.items()}}
        timing["fusion_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # 4) Section Parent Boost（spec §19：轻量 prior，禁止硬过滤）
        if mode == "hybrid" and cfg.fusion.parent_boost_enabled and "dense" in ranked_lists:
            t0 = time.perf_counter()
            section_hits, _ = self.dense.search(
                query, k=cfg.fusion.parent_boost_sections_k,
                collection=cfg.qdrant.sections_collection)
            # section_id(doc 无前缀) -> chunk_id 前缀匹配（M04:ch3-2:xxxx）
            boost_prefixes = {
                f"{h['payload']['document_id']}:{h['payload']['section_id']}:" for h in section_hits
            }
            for cid, c in candidates.items():
                if any(cid.startswith(p) for p in boost_prefixes):
                    c.section_boost = cfg.fusion.parent_boost
                c.final_score = c.rrf_score * c.section_boost
            timing["section_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            if debug:
                debug_trace["boosted_sections"] = sorted(
                    f"{h['payload']['document_id']}:{h['payload']['section_id']}" for h in section_hits)
        else:
            for c in candidates.values():
                c.final_score = c.rrf_score

        # 5) Metadata 过滤（lexical 路无法 prefilter，统一 post-filter）
        t0 = time.perf_counter()
        ordered = sorted(candidates.values(), key=lambda c: c.final_score, reverse=True)
        if filters:
            ordered = self._apply_filters(ordered, filters)
        fused_k = cfg.retrieval.fused_k
        ordered = ordered[:fused_k]
        timing["filter_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # 6) 组装结果（snippet/title 从 SQLite 取；rerank 可选）
        final_k = top_k or cfg.retrieval.final_k
        rows = self._fetch_rows([c.chunk_id for c in ordered])
        rows_by_id = {r["id"]: r for r in rows}
        timing_rerank = 0.0
        rerank_trace: list[dict] | None = None
        pre_rank_map: dict[str, int] = {}
        score_by_id: dict[str, float] = {}

        if rerank and self.reranker is not None and ordered:
            t0 = time.perf_counter()
            rerank_candidates = []
            for c in ordered:
                r = rows_by_id.get(c.chunk_id)
                if r is None:
                    continue
                rerank_candidates.append({
                    "chunk_id": c.chunk_id, "title": r["title"],
                    "heading_path": r["heading_path"], "content_type": r["content_type"],
                    "evidence_level": r["evidence_level"], "plain_text": r["plain_text"],
                })
            try:
                reranked = self.reranker.rerank(query, rerank_candidates)
                pre_rank_map = {c.chunk_id: i for i, c in enumerate(ordered, 1)}
                score_by_id = {x["chunk_id"]: x["reranker_score"] for x in reranked}
                # 重排：reranker 分数降序；未送入 rerank 的候选沉底（-inf）
                ordered = sorted(
                    ordered,
                    key=lambda c: score_by_id.get(c.chunk_id, float("-inf")),
                    reverse=True,
                )
                timing_rerank = round((time.perf_counter() - t0) * 1000, 2)
                if debug:
                    rerank_trace = [
                        {"chunk_id": x["chunk_id"], "reranker_score": round(x["reranker_score"], 4),
                         "pre_rerank_rank": pre_rank_map.get(x["chunk_id"])}
                        for x in reranked
                    ]
            except Exception as exc:
                logger.warning("rerank 失败，退回 RRF 排序: %s", exc)

        results = []
        for rank, c in enumerate(ordered[:final_k], 1):
            row = rows_by_id.get(c.chunk_id)
            if row is None:
                continue  # 索引与 catalog 不同步（M8 reconcile 处理）
            snippet = _make_snippet(row["plain_text"], query)
            results.append({
                "rank": rank,
                "chunk_id": c.chunk_id,
                "document_id": row["document_id"],
                "title": row["title"],
                "section_id": row["section_id"],
                "heading_path": row["heading_path"],
                "content_type": row["content_type"],
                "evidence_level": row["evidence_level"],
                "snippet": snippet,
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "scores": {
                    "dense_rank": c.ranks.get("dense"),
                    "terms_rank": c.ranks.get("terms"),
                    "trigram_rank": c.ranks.get("trigram"),
                    "rrf": round(c.rrf_score, 6),
                    "section_boost": c.section_boost,
                    "final": round(c.final_score, 6),
                    "reranker": round(score_by_id[c.chunk_id], 4) if rerank and score_by_id.get(c.chunk_id) is not None else None,
                    "pre_rerank_rank": pre_rank_map.get(c.chunk_id) if rerank else None,
                },
            })

        timing["rerank_ms"] = timing_rerank
        timing["total_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
        resp: dict[str, Any] = {"query": query, "mode": mode, "results": results, "timing_ms": timing}
        if debug:
            debug_trace["candidates_before_filter"] = len(candidates)
            debug_trace["fused_top"] = [
                {"chunk_id": c.chunk_id, "ranks": c.ranks, "rrf": round(c.rrf_score, 6),
                 "boost": c.section_boost} for c in ordered[:20]]
            debug_trace["filters"] = filters or {}
            if rerank_trace is not None:
                debug_trace["rerank"] = rerank_trace
            resp["debug"] = debug_trace
        return resp

    def _fetch_rows(self, chunk_ids: list[str]) -> list[sqlite3.Row]:
        if not chunk_ids:
            return []
        marks = ",".join("?" * len(chunk_ids))
        return self.conn.execute(
            f"SELECT c.id, c.document_id, c.section_id, c.heading_path, c.content_type, "
            f"c.evidence_level, c.plain_text, c.start_line, c.end_line, d.title "
            f"FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
            f"WHERE c.id IN ({marks})",
            chunk_ids,
        ).fetchall()

    def _apply_filters(self, candidates: list[Candidate], filters: dict) -> list[Candidate]:
        """按 chunks 表列过滤（document_ids/domains/evidence_levels/content_types/date）。"""
        clauses, params = [], []
        if filters.get("document_ids"):
            marks = ",".join("?" * len(filters["document_ids"]))
            clauses.append(f"document_id IN ({marks})")
            params += filters["document_ids"]
        if filters.get("domains"):
            marks = ",".join("?" * len(filters["domains"]))
            clauses.append(f"document_id IN (SELECT id FROM documents WHERE domain IN ({marks}))")
            params += filters["domains"]
        if filters.get("content_types"):
            marks = ",".join("?" * len(filters["content_types"]))
            clauses.append(f"content_type IN ({marks})")
            params += filters["content_types"]
        if filters.get("evidence_levels"):
            marks = ",".join("?" * len(filters["evidence_levels"]))
            clauses.append(f"evidence_level IN ({marks})")
            params += filters["evidence_levels"]
        if filters.get("date_from"):
            clauses.append("document_id IN (SELECT id FROM documents WHERE completed_at >= ?)")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            clauses.append("document_id IN (SELECT id FROM documents WHERE completed_at <= ?)")
            params.append(filters["date_to"])
        if not clauses:
            return candidates
        sql = f"SELECT id FROM chunks WHERE {' AND '.join(clauses)}"
        allowed = {r["id"] for r in self.conn.execute(sql, params).fetchall()}
        return [c for c in candidates if c.chunk_id in allowed]


def _make_snippet(plain_text: str, query: str, width: int = 200) -> str:
    """优先取首个查询词命中窗口，否则取开头。"""
    from app.lexical.normalizer import extract_identifiers

    terms = extract_identifiers(query) + [t for t in query.split() if len(t) >= 2]
    pos = -1
    for t in terms:
        pos = plain_text.find(t)
        if pos >= 0:
            break
    if pos < 0:
        return plain_text[:width] + ("…" if len(plain_text) > width else "")
    start = max(0, pos - width // 4)
    return ("…" if start > 0 else "") + plain_text[start : start + width] + (
        "…" if start + width < len(plain_text) else "")
