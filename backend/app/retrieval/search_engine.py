"""Hybrid Search Engine（M6 + P1 scoped lexical pre-filter）。

三路候选（Dense / Terms / Trigram）-> Weighted RRF -> 去重 ->
Section Parent Boost -> Metadata 最终过滤 -> Top-K。

Dense 与 Lexical 都在候选召回阶段尽可能应用 metadata pre-filter；最终仍保留
统一 post-filter 作为融合后的 correctness boundary。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import Config
from app.lexical.fts_search import LexicalSearcher
from app.retrieval.fusion import weighted_rrf

if TYPE_CHECKING:
    from app.retrieval.dense import DenseRetriever
    from app.retrieval.rerank import RerankerService

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    chunk_id: str
    document_id: str = ""
    section_id: str = ""
    ranks: dict[str, int | None] = field(default_factory=dict)
    rrf_score: float = 0.0
    section_boost: float = 1.0
    final_score: float = 0.0

    @property
    def merged_section_id(self) -> str:
        return self.section_id


class SearchEngine:
    def __init__(self, cfg: Config, conn: sqlite3.Connection, dense: "DenseRetriever",
                 reranker: "RerankerService | None" = None, *,
                 chunks_collection: str | None = None,
                 sections_collection: str | None = None,
                 section_boost_enabled: bool = True) -> None:
        self.cfg = cfg
        self.conn = conn
        self.dense = dense
        self.lexical = LexicalSearcher(conn)
        self.reranker = reranker
        self.chunks_collection = chunks_collection or cfg.qdrant.chunks_collection
        self.sections_collection = sections_collection or cfg.qdrant.sections_collection
        self.section_boost_enabled = section_boost_enabled

    def search(
        self,
        query: str,
        *,
        mode: str = "hybrid",
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

        # 1) Dense：Qdrant metadata filter 在 vector LIMIT 前执行。
        if mode in ("hybrid", "dense"):
            t0 = time.perf_counter()
            dense_hits, embed_ms = self.dense.search(
                query, k=cfg.retrieval.dense_k, filters=filters,
                collection=self.chunks_collection)
            timing["embed_ms"] = embed_ms
            timing["dense_ms"] = round((time.perf_counter() - t0) * 1000 - embed_ms, 2)
            ranked_lists["dense"] = [h["payload"]["chunk_id"] for h in dense_hits]
            dense_scores = {h["payload"]["chunk_id"]: h for h in dense_hits}
            for cid, h in dense_scores.items():
                candidates.setdefault(cid, Candidate(chunk_id=cid)).ranks["dense"] = None
                candidates[cid].document_id = h["payload"].get("document_id", "")
                candidates[cid].section_id = h["payload"].get("section_id", "")
            if debug:
                debug_trace["sources"]["dense"] = [
                    {"chunk_id": h["payload"]["chunk_id"], "score": h.get("score")}
                    for h in dense_hits[:20]
                ]

        # 2) Lexical：terms + trigram（在 FTS LIMIT 前应用 metadata pre-filter）。
        if mode in ("hybrid", "lexical"):
            lexical_results, lex_timing = self.lexical.search_combined(
                query,
                terms_k=cfg.retrieval.terms_k,
                trigram_k=cfg.retrieval.trigram_k,
                rrf_k=cfg.retrieval.rrf_k,
                terms_weight=cfg.retrieval.terms_weight,
                trigram_weight=cfg.retrieval.trigram_weight,
                filters=filters,
            )
            timing.update(lex_timing)
            ranked_lists["lexical"] = [cid for cid, _, _ in lexical_results]
            for cid, _score, ranks in lexical_results:
                candidate = candidates.setdefault(cid, Candidate(chunk_id=cid))
                for source, rank in ranks.items():
                    candidate.ranks[source] = rank
            if debug:
                debug_trace["sources"]["lexical"] = [
                    {"chunk_id": cid, "score": score, "ranks": ranks}
                    for cid, score, ranks in lexical_results[:20]
                ]

        # 3) Weighted RRF across the active source lists.
        t0 = time.perf_counter()
        rrf_lists: list[list[str]] = []
        rrf_weights: list[float] = []
        if ranked_lists.get("dense"):
            rrf_lists.append(ranked_lists["dense"])
            rrf_weights.append(cfg.retrieval.dense_weight)
        if ranked_lists.get("lexical"):
            rrf_lists.append(ranked_lists["lexical"])
            rrf_weights.append(1.0)
        if rrf_lists:
            fused = weighted_rrf(rrf_lists, rrf_weights, k=cfg.retrieval.rrf_k)
            for cid, score in fused:
                candidates.setdefault(cid, Candidate(chunk_id=cid)).rrf_score = score
        timing["fusion_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # 4) Canonical SQLite enrichment + final metadata filter.
        t0 = time.perf_counter()
        candidates = self._enrich_and_filter(candidates, filters)
        timing["filter_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # 5) Optional parent-section semantic boost. Dense is lazy, so lexical mode
        # never reaches this path unless semantic section boosting is relevant.
        if self.section_boost_enabled and mode in ("hybrid", "dense") and candidates:
            t0 = time.perf_counter()
            self._apply_section_boost(query, candidates)
            timing["section_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        for candidate in candidates.values():
            candidate.final_score = candidate.rrf_score * candidate.section_boost

        ordered = sorted(candidates.values(), key=lambda c: c.final_score, reverse=True)
        limit = top_k or cfg.retrieval.top_k
        ordered = ordered[:limit]

        results = self._materialize(ordered)

        # 6) Optional reranker: explicit only and never required by lexical base path.
        if rerank and self.reranker is not None and results:
            try:
                results = self.reranker.rerank(query, results, top_k=limit)
            except Exception as exc:
                logger.warning("rerank failed; keep retrieval order: %s", exc)
                if debug:
                    debug_trace["rerank_error"] = f"{type(exc).__name__}: {exc}"

        timing["total_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
        response: dict[str, Any] = {
            "query": query,
            "mode": mode,
            "results": results,
            "timing_ms": timing,
        }
        if debug:
            debug_trace["final"] = [
                {
                    "chunk_id": c.chunk_id,
                    "rrf_score": c.rrf_score,
                    "section_boost": c.section_boost,
                    "final_score": c.final_score,
                    "ranks": c.ranks,
                }
                for c in ordered
            ]
            response["debug"] = debug_trace
        return response

    def _enrich_and_filter(
        self,
        candidates: dict[str, Candidate],
        filters: dict | None,
    ) -> dict[str, Candidate]:
        if not candidates:
            return candidates
        ids = list(candidates)
        enriched: dict[str, Candidate] = {}
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = self.conn.execute(
                f"SELECT c.id, c.document_id, c.section_id, c.content_type, "
                f"c.evidence_level, d.domain, d.completed_at "
                f"FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
                f"WHERE c.id IN ({placeholders})",
                batch,
            ).fetchall()
            for row in rows:
                if not self._matches_filters(row, filters):
                    continue
                candidate = candidates[row["id"]]
                candidate.document_id = row["document_id"]
                candidate.section_id = row["section_id"] or ""
                enriched[row["id"]] = candidate
        return enriched

    @staticmethod
    def _matches_filters(row, filters: dict | None) -> bool:
        if not filters:
            return True
        if filters.get("document_ids") and row["document_id"] not in filters["document_ids"]:
            return False
        if filters.get("domains") and row["domain"] not in filters["domains"]:
            return False
        if filters.get("content_types") and row["content_type"] not in filters["content_types"]:
            return False
        if filters.get("evidence_levels") and row["evidence_level"] not in filters["evidence_levels"]:
            return False
        if filters.get("date_from") and (row["completed_at"] or "") < filters["date_from"]:
            return False
        if filters.get("date_to") and (row["completed_at"] or "") > filters["date_to"]:
            return False
        return True

    def _apply_section_boost(self, query: str, candidates: dict[str, Candidate]) -> None:
        section_ids = sorted({c.section_id for c in candidates.values() if c.section_id})
        if not section_ids:
            return
        hits, _embed_ms = self.dense.search(
            query,
            k=max(len(section_ids), min(self.cfg.retrieval.section_k, 100)),
            collection=self.sections_collection,
        )
        scores: dict[str, float] = {}
        for hit in hits:
            payload = hit.get("payload") or {}
            sid = payload.get("section_id")
            if sid:
                scores[sid] = float(hit.get("score") or 0.0)
        for candidate in candidates.values():
            section_score = scores.get(candidate.section_id)
            if section_score is None:
                continue
            candidate.section_boost = 1.0 + max(0.0, section_score) * self.cfg.retrieval.section_boost

    def _materialize(self, ordered: list[Candidate]) -> list[dict[str, Any]]:
        if not ordered:
            return []
        ids = [c.chunk_id for c in ordered]
        rows_by_id: dict[str, Any] = {}
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = self.conn.execute(
                f"SELECT c.id, c.document_id, c.section_id, c.heading, c.heading_path, "
                f"c.text, c.start_line, c.end_line, c.content_type, c.evidence_level, "
                f"d.title AS document_title, d.domain, d.completed_at "
                f"FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
                f"WHERE c.id IN ({placeholders})",
                batch,
            ).fetchall()
            rows_by_id.update({row["id"]: row for row in rows})

        results: list[dict[str, Any]] = []
        for rank, candidate in enumerate(ordered, start=1):
            row = rows_by_id.get(candidate.chunk_id)
            if row is None:
                continue
            text = row["text"] or ""
            snippet = re.sub(r"\s+", " ", text).strip()[:500]
            result = {
                "rank": rank,
                "chunk_id": candidate.chunk_id,
                "document_id": row["document_id"],
                "document_title": row["document_title"] or row["document_id"],
                "heading": row["heading"] or "",
                "heading_path": row["heading_path"] or "",
                "snippet": snippet,
                "text": text,
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "content_type": row["content_type"],
                "evidence_level": row["evidence_level"],
                "domain": row["domain"],
                "completed_at": row["completed_at"],
                "score": candidate.final_score,
                "rrf_score": candidate.rrf_score,
                "section_boost": candidate.section_boost,
                "ranks": candidate.ranks,
            }
            results.append(result)
        return results
