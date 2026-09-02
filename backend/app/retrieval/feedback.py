"""Personal retrieval feedback persistence.

This is intentionally small and local-first: one row per search result exposure, then
explicit user interactions update that row. The resulting table provides a real
ranking denominator before any future tuning of retrieval weights or model settings.

The schema is created lazily on the report-search SQLite connection instead of the
shared catalog migration so the separate Cognition catalog is not polluted with an
unused feedback table.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS retrieval_feedback (
        id TEXT PRIMARY KEY,
        search_id TEXT NOT NULL,
        query TEXT NOT NULL,
        chunk_id TEXT NOT NULL,
        rank INTEGER NOT NULL,
        mode TEXT NOT NULL,
        useful INTEGER,
        selected_as_evidence INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(search_id, chunk_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_created ON retrieval_feedback(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_chunk ON retrieval_feedback(chunk_id)",
    "CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_mode ON retrieval_feedback(mode)",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_feedback_schema(conn: sqlite3.Connection) -> None:
    """Idempotently initialize feedback storage on the supplied report connection only."""

    with conn:
        for statement in _SCHEMA_SQL:
            conn.execute(statement)


def record_search_results(
    conn: sqlite3.Connection,
    *,
    query: str,
    mode: str,
    results: list[dict],
) -> str:
    """Persist one exposure row for every returned result and return a search_id."""

    ensure_feedback_schema(conn)
    search_id = uuid4().hex
    created_at = _now()
    rows = [
        (
            uuid4().hex,
            search_id,
            query,
            str(result["chunk_id"]),
            int(result["rank"]),
            mode,
            None,
            0,
            created_at,
            created_at,
        )
        for result in results
    ]
    if rows:
        with conn:
            conn.executemany(
                """
                INSERT INTO retrieval_feedback(
                    id, search_id, query, chunk_id, rank, mode,
                    useful, selected_as_evidence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
    return search_id


def update_feedback(
    conn: sqlite3.Connection,
    *,
    search_id: str,
    chunk_id: str,
    useful: bool | None = None,
    selected_as_evidence: bool | None = None,
) -> dict | None:
    """Update explicit feedback for one result exposure.

    ``None`` means "leave this field unchanged". At least one feedback field must be
    supplied by the API layer.
    """

    ensure_feedback_schema(conn)
    assignments: list[str] = []
    values: list[object] = []
    if useful is not None:
        assignments.append("useful = ?")
        values.append(1 if useful else 0)
    if selected_as_evidence is not None:
        assignments.append("selected_as_evidence = ?")
        values.append(1 if selected_as_evidence else 0)
    if not assignments:
        return None

    assignments.append("updated_at = ?")
    values.append(_now())
    values.extend([search_id, chunk_id])
    with conn:
        cursor = conn.execute(
            f"UPDATE retrieval_feedback SET {', '.join(assignments)} "
            "WHERE search_id = ? AND chunk_id = ?",
            values,
        )
    if cursor.rowcount != 1:
        return None
    row = conn.execute(
        """
        SELECT search_id, query, chunk_id, rank, mode, useful,
               selected_as_evidence, created_at, updated_at
        FROM retrieval_feedback
        WHERE search_id = ? AND chunk_id = ?
        """,
        (search_id, chunk_id),
    ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    if payload["useful"] is not None:
        payload["useful"] = bool(payload["useful"])
    payload["selected_as_evidence"] = bool(payload["selected_as_evidence"])
    return payload
