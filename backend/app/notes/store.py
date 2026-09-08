"""KE-owned personal understanding notes (DL-08).

Not formal Cognition. Does not create Judgment / Proposal / Topic.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

STANCES = ("agree", "disagree", "question", "mechanism", "note")


def ensure_notes_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_notes (
            id TEXT PRIMARY KEY,
            chunk_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            heading_path TEXT,
            stance TEXT NOT NULL,
            body TEXT NOT NULL,
            task_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_personal_notes_chunk ON personal_notes(chunk_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_personal_notes_doc ON personal_notes(document_id)"
    )
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


class NoteStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        ensure_notes_schema(conn)

    def create(
        self,
        *,
        chunk_id: str,
        document_id: str,
        body: str,
        stance: str = "note",
        heading_path: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        body = (body or "").strip()
        if not body:
            raise ValueError("笔记正文不能为空")
        if stance not in STANCES:
            raise ValueError(f"stance 必须是 {STANCES}")
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        ts = _now()
        self.conn.execute(
            """
            INSERT INTO personal_notes
            (id, chunk_id, document_id, heading_path, stance, body, task_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (note_id, chunk_id, document_id, heading_path, stance, body, task_id, ts, ts),
        )
        self.conn.commit()
        return self.get(note_id)

    def get(self, note_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM personal_notes WHERE id = ?", (note_id,)
        ).fetchone()
        return _row(row) if row else None

    def list(
        self,
        *,
        chunk_id: str | None = None,
        document_id: str | None = None,
        q: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []
        if chunk_id:
            clauses.append("chunk_id = ?")
            params.append(chunk_id)
        if document_id:
            clauses.append("document_id = ?")
            params.append(document_id)
        if q:
            clauses.append("(body LIKE ? OR heading_path LIKE ? OR chunk_id LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM personal_notes {where} ORDER BY updated_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [_row(r) for r in rows]

    def update(self, note_id: str, *, body: str | None = None, stance: str | None = None) -> dict | None:
        current = self.get(note_id)
        if current is None:
            return None
        if body is not None:
            body = body.strip()
            if not body:
                raise ValueError("笔记正文不能为空")
            current["body"] = body
        if stance is not None:
            if stance not in STANCES:
                raise ValueError(f"stance 必须是 {STANCES}")
            current["stance"] = stance
        current["updated_at"] = _now()
        self.conn.execute(
            "UPDATE personal_notes SET body = ?, stance = ?, updated_at = ? WHERE id = ?",
            (current["body"], current["stance"], current["updated_at"], note_id),
        )
        self.conn.commit()
        return current

    def delete(self, note_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM personal_notes WHERE id = ?", (note_id,))
        self.conn.commit()
        return cur.rowcount > 0
