"""Personal Retrieval Feedback deterministic contracts."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.api.search as search_api
from app.retrieval.feedback import record_search_results, update_feedback
from app.storage.migrations import init_schema


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _results() -> list[dict]:
    return [
        {"rank": 1, "chunk_id": "doc:sec:0001"},
        {"rank": 2, "chunk_id": "doc:sec:0002"},
    ]


def test_search_result_exposures_are_persisted_with_real_denominator():
    conn = _conn()
    search_id = record_search_results(conn, query="HBM4 接口", mode="lexical", results=_results())

    rows = conn.execute(
        "SELECT search_id, query, chunk_id, rank, mode, useful, selected_as_evidence, created_at "
        "FROM retrieval_feedback ORDER BY rank"
    ).fetchall()
    assert len(rows) == 2
    assert {row["search_id"] for row in rows} == {search_id}
    assert [row["rank"] for row in rows] == [1, 2]
    assert all(row["query"] == "HBM4 接口" for row in rows)
    assert all(row["mode"] == "lexical" for row in rows)
    assert all(row["useful"] is None for row in rows)
    assert all(row["selected_as_evidence"] == 0 for row in rows)
    assert all(row["created_at"] for row in rows)


def test_feedback_updates_existing_exposure_in_place():
    conn = _conn()
    search_id = record_search_results(conn, query="HBM4 接口", mode="hybrid", results=_results())

    first = update_feedback(
        conn,
        search_id=search_id,
        chunk_id="doc:sec:0001",
        useful=True,
    )
    assert first is not None
    assert first["useful"] is True
    assert first["selected_as_evidence"] is False

    second = update_feedback(
        conn,
        search_id=search_id,
        chunk_id="doc:sec:0001",
        selected_as_evidence=True,
    )
    assert second is not None
    assert second["useful"] is True
    assert second["selected_as_evidence"] is True
    assert conn.execute("SELECT count(*) FROM retrieval_feedback").fetchone()[0] == 2


def test_repeated_query_creates_distinct_search_samples():
    conn = _conn()
    first = record_search_results(conn, query="同一问题", mode="lexical", results=_results())
    second = record_search_results(conn, query="同一问题", mode="lexical", results=_results())

    assert first != second
    assert conn.execute("SELECT count(*) FROM retrieval_feedback").fetchone()[0] == 4


def test_update_rejects_unknown_exposure():
    conn = _conn()
    assert update_feedback(
        conn,
        search_id="missing",
        chunk_id="missing",
        useful=False,
    ) is None


def test_feedback_request_requires_at_least_one_explicit_signal():
    with pytest.raises(ValidationError):
        search_api.RetrievalFeedbackUpdate(search_id="s1", chunk_id="c1")


class _FakeEngine:
    def search(self, query, *, mode, top_k, filters, debug, rerank):
        return {
            "query": query,
            "mode": mode,
            "results": _results(),
            "timing_ms": {"total_ms": 1},
        }


def _request(conn: sqlite3.Connection):
    state = SimpleNamespace(conn=conn, engine=_FakeEngine(), qdrant_available=True)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_report_search_returns_search_id_and_records_exposures():
    conn = _conn()
    body = search_api.SearchRequest(
        query="真实搜索",
        options=search_api.SearchOptions(mode="lexical", rerank=False, top_k=10),
    )

    response = search_api.search(body, _request(conn))
    assert response["search_id"]
    rows = conn.execute(
        "SELECT query, mode, rank, chunk_id FROM retrieval_feedback WHERE search_id = ? ORDER BY rank",
        (response["search_id"],),
    ).fetchall()
    assert [(r["rank"], r["chunk_id"]) for r in rows] == [
        (1, "doc:sec:0001"),
        (2, "doc:sec:0002"),
    ]
    assert all(r["query"] == "真实搜索" and r["mode"] == "lexical" for r in rows)


def test_feedback_storage_failure_does_not_break_search(monkeypatch):
    conn = _conn()

    def fail(**_kwargs):
        raise sqlite3.OperationalError("simulated write failure")

    monkeypatch.setattr(search_api, "record_search_results", fail)
    body = search_api.SearchRequest(
        query="搜索仍应成功",
        options=search_api.SearchOptions(mode="lexical", rerank=False),
    )
    response = search_api.search(body, _request(conn))
    assert response["results"]
    assert response["search_id"] is None


def test_feedback_api_updates_row_and_returns_404_for_unknown():
    conn = _conn()
    search_id = record_search_results(conn, query="反馈", mode="lexical", results=_results())
    request = _request(conn)

    updated = search_api.retrieval_feedback(
        search_api.RetrievalFeedbackUpdate(
            search_id=search_id,
            chunk_id="doc:sec:0002",
            useful=False,
            selected_as_evidence=True,
        ),
        request,
    )
    assert updated["useful"] is False
    assert updated["selected_as_evidence"] is True

    with pytest.raises(HTTPException) as exc:
        search_api.retrieval_feedback(
            search_api.RetrievalFeedbackUpdate(
                search_id="unknown",
                chunk_id="unknown",
                useful=True,
            ),
            request,
        )
    assert exc.value.status_code == 404
