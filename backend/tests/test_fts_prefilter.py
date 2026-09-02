"""P1 regression: lexical metadata filters must run before FTS LIMIT."""

import sqlite3

from app.lexical.fts_search import LexicalSearcher


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            domain TEXT,
            completed_at TEXT
        );
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT,
            content_type TEXT,
            evidence_level INTEGER
        );
        CREATE VIRTUAL TABLE chunks_fts_terms USING fts5(
            chunk_id UNINDEXED,
            document_id UNINDEXED,
            heading,
            lexical_text
        );
        CREATE VIRTUAL TABLE chunks_fts_trigram USING fts5(
            chunk_id UNINDEXED,
            document_id UNINDEXED,
            heading,
            raw_text,
            tokenize='trigram'
        );
        """
    )
    conn.executemany(
        "INSERT INTO documents(id, domain, completed_at) VALUES (?, ?, ?)",
        [
            ("A", "semiconductor", "2025-01-01"),
            ("B", "macro", "2026-06-30"),
        ],
    )

    rows = [
        ("A:1", "A", "fact", 3, "alpha alpha alpha alpha alpha"),
        ("A:2", "A", "fact", 3, "alpha alpha alpha alpha"),
        ("A:3", "A", "fact", 2, "alpha alpha alpha"),
        # This is deliberately weaker globally, but must be rank 1 inside scope B.
        ("B:1", "B", "causal_chain", 1, "alpha"),
    ]
    for chunk_id, doc_id, content_type, evidence_level, text in rows:
        conn.execute(
            "INSERT INTO chunks(id, document_id, content_type, evidence_level) VALUES (?, ?, ?, ?)",
            (chunk_id, doc_id, content_type, evidence_level),
        )
        conn.execute(
            "INSERT INTO chunks_fts_terms(chunk_id, document_id, heading, lexical_text) VALUES (?, ?, ?, ?)",
            (chunk_id, doc_id, "h", text),
        )
        conn.execute(
            "INSERT INTO chunks_fts_trigram(chunk_id, document_id, heading, raw_text) VALUES (?, ?, ?, ?)",
            (chunk_id, doc_id, "h", text),
        )
    conn.commit()
    return conn


def test_document_filter_applies_before_limit():
    searcher = LexicalSearcher(_db())
    global_hit = searcher.search_terms("alpha", k=1)
    assert global_hit[0].document_id == "A"

    scoped = searcher.search_terms("alpha", k=1, filters={"document_ids": ["B"]})
    assert [hit.chunk_id for hit in scoped] == ["B:1"]


def test_domain_filter_applies_before_limit():
    searcher = LexicalSearcher(_db())
    scoped = searcher.search_terms("alpha", k=1, filters={"domains": ["macro"]})
    assert [hit.chunk_id for hit in scoped] == ["B:1"]


def test_content_type_and_evidence_filters_apply_before_limit():
    searcher = LexicalSearcher(_db())
    scoped = searcher.search_terms(
        "alpha",
        k=1,
        filters={"content_types": ["causal_chain"], "evidence_levels": [1]},
    )
    assert [hit.chunk_id for hit in scoped] == ["B:1"]


def test_date_filter_applies_before_limit():
    searcher = LexicalSearcher(_db())
    scoped = searcher.search_terms("alpha", k=1, filters={"date_from": "2026-01-01"})
    assert [hit.chunk_id for hit in scoped] == ["B:1"]


def test_combined_propagates_filters_to_both_fts_routes():
    searcher = LexicalSearcher(_db())
    fused, _ = searcher.search_combined(
        "alpha",
        terms_k=1,
        trigram_k=1,
        filters={"document_ids": ["B"]},
    )
    assert fused
    assert fused[0][0] == "B:1"
