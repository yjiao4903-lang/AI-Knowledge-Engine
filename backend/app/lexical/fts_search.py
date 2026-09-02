"""FTS5 Lexical 检索（M4 + P1 scoped pre-filter）。

三种模式：terms / trigram / lexical_combined（RRF 融合，不混原始 BM25 分）。
Metadata filters are applied inside the FTS query *before* ORDER BY/LIMIT so a
scoped search cannot lose a relevant hit merely because it ranked below the
global candidate cutoff.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from app.core.errors import SqliteError
from app.lexical.query_parser import build_terms_expression, build_trigram_expression
from app.retrieval.fusion import weighted_rrf


@dataclass
class LexicalHit:
    chunk_id: str
    document_id: str
    heading: str
    rank: int
    score: float  # bm25（越小越相关）或 rrf 分


def _filter_sql(filters: dict[str, Any] | None) -> tuple[list[str], list[Any]]:
    """Build filter clauses against canonical chunks/documents metadata.

    The caller joins the FTS table to `chunks c` and `documents d`, so every
    supported filter is evaluated before FTS LIMIT. Empty filter lists mean no
    restriction, matching SearchEngine's historical post-filter semantics.
    """
    if not filters:
        return [], []

    clauses: list[str] = []
    params: list[Any] = []

    if filters.get("document_ids"):
        values = list(filters["document_ids"])
        clauses.append(f"c.document_id IN ({','.join('?' for _ in values)})")
        params.extend(values)
    if filters.get("domains"):
        values = list(filters["domains"])
        clauses.append(f"d.domain IN ({','.join('?' for _ in values)})")
        params.extend(values)
    if filters.get("content_types"):
        values = list(filters["content_types"])
        clauses.append(f"c.content_type IN ({','.join('?' for _ in values)})")
        params.extend(values)
    if filters.get("evidence_levels"):
        values = list(filters["evidence_levels"])
        clauses.append(f"c.evidence_level IN ({','.join('?' for _ in values)})")
        params.extend(values)
    if filters.get("date_from"):
        clauses.append("d.completed_at >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("d.completed_at <= ?")
        params.append(filters["date_to"])

    return clauses, params


def _search(
    conn: sqlite3.Connection,
    table: str,
    expression: str,
    k: int,
    filters: dict[str, Any] | None = None,
) -> list[LexicalHit]:
    if not expression:
        return []

    filter_clauses, filter_params = _filter_sql(filters)
    where = [f"{table} MATCH ?", *filter_clauses]
    sql = (
        f"SELECT {table}.chunk_id, {table}.document_id, {table}.heading, "
        f"bm25({table}) AS score "
        f"FROM {table} "
        f"JOIN chunks c ON c.id = {table}.chunk_id "
        f"LEFT JOIN documents d ON d.id = c.document_id "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY score LIMIT ?"
    )
    params = [expression, *filter_params, k]

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise SqliteError(
            f"FTS 查询语法错误: {exc}",
            detail={"expression": expression, "filters": filters or {}},
        ) from exc
    return [
        LexicalHit(r["chunk_id"], r["document_id"], r["heading"], i + 1, r["score"])
        for i, r in enumerate(rows)
    ]


class LexicalSearcher:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        terms_table: str = "chunks_fts_terms",
        trigram_table: str = "chunks_fts_trigram",
    ) -> None:
        self.conn = conn
        self.terms_table = terms_table
        self.trigram_table = trigram_table

    def search_terms(
        self,
        query: str,
        k: int = 50,
        *,
        filters: dict[str, Any] | None = None,
    ) -> list[LexicalHit]:
        return _search(
            self.conn,
            self.terms_table,
            build_terms_expression(query),
            k,
            filters,
        )

    def search_trigram(
        self,
        query: str,
        k: int = 30,
        *,
        filters: dict[str, Any] | None = None,
    ) -> list[LexicalHit]:
        return _search(
            self.conn,
            self.trigram_table,
            build_trigram_expression(query),
            k,
            filters,
        )

    def search_combined(
        self,
        query: str,
        *,
        terms_k: int = 50,
        trigram_k: int = 30,
        rrf_k: int = 60,
        terms_weight: float = 0.9,
        trigram_weight: float = 0.7,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[tuple[str, float, dict]], dict[str, float]]:
        """返回 (融合结果 [(chunk_id, rrf, ranks)], timing_ms)。"""
        t0 = time.perf_counter()
        terms_hits = self.search_terms(query, terms_k, filters=filters)
        t1 = time.perf_counter()
        trigram_hits = self.search_trigram(query, trigram_k, filters=filters)
        t2 = time.perf_counter()

        fused = weighted_rrf(
            {
                "terms": [h.chunk_id for h in terms_hits],
                "trigram": [h.chunk_id for h in trigram_hits],
            },
            rrf_k=rrf_k,
            weights={"terms": terms_weight, "trigram": trigram_weight},
        )
        t3 = time.perf_counter()
        timing = {
            "terms_ms": round((t1 - t0) * 1000, 2),
            "trigram_ms": round((t2 - t1) * 1000, 2),
            "fusion_ms": round((t3 - t2) * 1000, 2),
        }
        return fused, timing
