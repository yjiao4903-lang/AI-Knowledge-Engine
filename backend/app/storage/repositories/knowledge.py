"""Repository 层（M1-08）。

documents / sections / chunks / FTS / indexing_jobs 的读写入口。
SQLite 是 Canonical Knowledge Catalog；Qdrant/FTS 的写入与文档表同事务提交。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from app.core.errors import SqliteError


class DocumentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    _COLS = (
        "id, report_code, title, domain, report_type, research_method, author, "
        "completed_at, language, status, source_path, file_name, file_size, "
        "file_mtime_ns, sha256, parser_version, chunker_version, schema_version, "
        "indexed_at, created_at, updated_at"
    )

    def upsert(self, doc: dict[str, Any]) -> None:
        keys = self._COLS.split(", ")
        values = [doc.get(k) for k in keys]
        placeholders = ", ".join(["?"] * len(keys))
        updates = ", ".join(f"{k} = excluded.{k}" for k in keys if k not in ("id", "created_at"))
        try:
            self.conn.execute(
                f"INSERT INTO documents ({self._COLS}) VALUES ({placeholders}) "
                f"ON CONFLICT(id) DO UPDATE SET {updates}, updated_at = excluded.updated_at",
                values,
            )
        except sqlite3.Error as exc:
            raise SqliteError(f"documents upsert 失败: {doc.get('id')}") from exc

    def get(self, doc_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT {self._COLS} FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_source_path(self, source_path: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT {self._COLS} FROM documents WHERE source_path = ?", (source_path,)
        ).fetchone()
        return dict(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(f"SELECT {self._COLS} FROM documents ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def delete(self, doc_id: str) -> None:
        # chunks/sections 由外键级联语义处理：显式删除避免依赖 PRAGMA 顺序
        self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        self.conn.execute("DELETE FROM chunks_fts_terms WHERE document_id = ?", (doc_id,))
        self.conn.execute("DELETE FROM chunks_fts_trigram WHERE document_id = ?", (doc_id,))
        self.conn.execute("DELETE FROM sections WHERE document_id = ?", (doc_id,))
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


class SectionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    _COLS = (
        "id, document_id, parent_section_id, level, heading, heading_path, "
        "section_type, ordinal, start_line, end_line, raw_text, summary_text"
    )

    def replace_for_document(self, sections: list[dict[str, Any]]) -> None:
        """整篇替换（staging 调用方保证同一事务内先删旧数据）。"""
        if not sections:
            return
        doc_id = sections[0]["document_id"]
        self.conn.execute("DELETE FROM sections WHERE document_id = ?", (doc_id,))
        keys = self._COLS.split(", ")
        placeholders = ", ".join(["?"] * len(keys))
        self.conn.executemany(
            f"INSERT INTO sections ({self._COLS}) VALUES ({placeholders})",
            [[s.get(k) for k in keys] for s in sections],
        )

    def list_for_document(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            f"SELECT {self._COLS} FROM sections WHERE document_id = ? ORDER BY ordinal", (doc_id,)
        ).fetchall()
        return [dict(r) for r in rows]


class ChunkRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    _COLS = (
        "id, document_id, section_id, ordinal, heading_path, content_type, "
        "raw_markdown, plain_text, embedding_text, lexical_text, evidence_level, "
        "evidence_levels_json, entities_json, tags_json, time_mentions_json, "
        "start_line, end_line, content_hash"
    )

    def upsert_batch(self, chunks: list[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        keys = self._COLS.split(", ")
        placeholders = ", ".join(["?"] * len(keys))
        self.conn.executemany(
            f"INSERT INTO chunks ({self._COLS}) VALUES ({placeholders}) "
            "ON CONFLICT(id) DO UPDATE SET " + ", ".join(
                f"{k} = excluded.{k}" for k in keys if k not in ("id",)
            ),
            [[c.get(k) for k in keys] for c in chunks],
        )
        self._sync_fts(chunks)
        return len(chunks)

    def _sync_fts(self, chunks: list[dict[str, Any]]) -> None:
        """FTS 双索引同步：terms（分词后）+ trigram（原文）。"""
        for c in chunks:
            self.conn.execute("DELETE FROM chunks_fts_terms WHERE chunk_id = ?", (c["id"],))
            self.conn.execute("DELETE FROM chunks_fts_trigram WHERE chunk_id = ?", (c["id"],))
        self.conn.executemany(
            "INSERT INTO chunks_fts_terms (chunk_id, document_id, heading, lexical_text) "
            "VALUES (?, ?, ?, ?)",
            [
                (c["id"], c["document_id"], c.get("heading_path", ""), c.get("lexical_text", ""))
                for c in chunks
            ],
        )
        self.conn.executemany(
            "INSERT INTO chunks_fts_trigram (chunk_id, document_id, heading, raw_text) "
            "VALUES (?, ?, ?, ?)",
            [
                (c["id"], c["document_id"], c.get("heading_path", ""), c.get("plain_text", ""))
                for c in chunks
            ],
        )

    def get(self, chunk_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT {self._COLS} FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_for_document(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            f"SELECT {self._COLS} FROM chunks WHERE document_id = ? ORDER BY ordinal", (doc_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM chunks").fetchone()[0]


class IndexJobRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, job_id: str, started_at: str) -> None:
        self.conn.execute(
            "INSERT INTO indexing_jobs (id, started_at, status) VALUES (?, ?, 'running')",
            (job_id, started_at),
        )

    def finish(
        self,
        job_id: str,
        finished_at: str,
        status: str,
        *,
        files_seen: int = 0,
        files_changed: int = 0,
        chunks_upserted: int = 0,
        chunks_deleted: int = 0,
        error_count: int = 0,
        error_json: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE indexing_jobs SET
                finished_at = ?, status = ?, files_seen = ?, files_changed = ?,
                chunks_upserted = ?, chunks_deleted = ?, error_count = ?, error_json = ?
            WHERE id = ?
            """,
            (finished_at, status, files_seen, files_changed, chunks_upserted,
             chunks_deleted, error_count, error_json, job_id),
        )
