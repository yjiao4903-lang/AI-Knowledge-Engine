"""FTS5 Lexical 检索（M4，Addendum §14-15）。

三种模式：terms / trigram / lexical_combined（RRF 融合，不混原始 BM25 分）。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

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


def _search(conn: sqlite3.Connection, table: str, expression: str, k: int) -> list[LexicalHit]:
    if not expression:
        return []
    try:
        rows = conn.execute(
            f"SELECT chunk_id, document_id, heading, bm25({table}) AS score "
            f"FROM {table} WHERE {table} MATCH ? "
            f"ORDER BY score LIMIT ?",
            (expression, k),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise SqliteError(f"FTS 查询语法错误: {exc}", detail={"expression": expression}) from exc
    return [LexicalHit(r["chunk_id"], r["document_id"], r["heading"], i + 1, r["score"]) for i, r in enumerate(rows)]


class LexicalSearcher:
    def __init__(self, conn: sqlite3.Connection, *, terms_table: str = "chunks_fts_terms",
                 trigram_table: str = "chunks_fts_trigram") -> None:
        self.conn = conn
        self.terms_table = terms_table
        self.trigram_table = trigram_table

    def search_terms(self, query: str, k: int = 50) -> list[LexicalHit]:
        return _search(self.conn, self.terms_table, build_terms_expression(query), k)

    def search_trigram(self, query: str, k: int = 30) -> list[LexicalHit]:
        return _search(self.conn, self.trigram_table, build_trigram_expression(query), k)

    def search_combined(
        self,
        query: str,
        *,
        terms_k: int = 50,
        trigram_k: int = 30,
        rrf_k: int = 60,
        terms_weight: float = 0.9,
        trigram_weight: float = 0.7,
    ) -> tuple[list[tuple[str, float, dict]], dict[str, float]]:
        """返回 (融合结果 [(chunk_id, rrf, ranks)], timing_ms)。"""
        t0 = time.perf_counter()
        terms_hits = self.search_terms(query, terms_k)
        t1 = time.perf_counter()
        trigram_hits = self.search_trigram(query, trigram_k)
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
