"""Schema migration（M1-05）。

- 全部表结构见 spec §8（documents/sections/chunks/indexing_jobs）与 §8.5/8.6（FTS）；
- init_schema 幂等：CREATE TABLE IF NOT EXISTS + meta 表记录 schema_version；
- FTS 用 external content 之外的独立表（chunk_id UNINDEXED），由写入侧同步维护。
"""

from __future__ import annotations

import sqlite3

from app.core.config import SCHEMA_VERSION
from app.core.errors import SqliteError

_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        report_code TEXT,
        title TEXT NOT NULL,
        domain TEXT,
        report_type TEXT,
        research_method TEXT,
        author TEXT,
        completed_at TEXT,
        language TEXT,
        status TEXT,
        source_path TEXT NOT NULL UNIQUE,
        file_name TEXT NOT NULL,
        file_size INTEGER,
        file_mtime_ns INTEGER,
        sha256 TEXT NOT NULL,
        parser_version TEXT,
        chunker_version TEXT,
        schema_version TEXT,
        indexed_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sections (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        parent_section_id TEXT,
        level INTEGER NOT NULL,
        heading TEXT NOT NULL,
        heading_path TEXT NOT NULL,
        section_type TEXT,
        ordinal INTEGER,
        start_line INTEGER,
        end_line INTEGER,
        raw_text TEXT,
        summary_text TEXT,
        FOREIGN KEY(document_id) REFERENCES documents(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sections_document ON sections(document_id)",
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        section_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        heading_path TEXT NOT NULL,
        content_type TEXT NOT NULL,
        raw_markdown TEXT NOT NULL,
        plain_text TEXT NOT NULL,
        embedding_text TEXT NOT NULL,
        lexical_text TEXT NOT NULL,
        evidence_level INTEGER,
        evidence_levels_json TEXT,
        entities_json TEXT,
        tags_json TEXT,
        time_mentions_json TEXT,
        start_line INTEGER,
        end_line INTEGER,
        content_hash TEXT NOT NULL,
        FOREIGN KEY(document_id) REFERENCES documents(id),
        FOREIGN KEY(section_id) REFERENCES sections(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_id)",
    """
    CREATE TABLE IF NOT EXISTS indexing_jobs (
        id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        files_seen INTEGER DEFAULT 0,
        files_changed INTEGER DEFAULT 0,
        chunks_upserted INTEGER DEFAULT 0,
        chunks_deleted INTEGER DEFAULT 0,
        error_count INTEGER DEFAULT 0,
        error_json TEXT
    )
    """,
    # 删除文件 Tombstone（spec §25）
    """
    CREATE TABLE IF NOT EXISTS document_tombstones (
        source_path TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        last_sha256 TEXT NOT NULL,
        deleted_at TEXT NOT NULL
    )
    """,
    # FTS Terms（lexical_text 已由 Python 分词）
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts_terms USING fts5(
        chunk_id UNINDEXED,
        document_id UNINDEXED,
        heading,
        lexical_text,
        tokenize = 'unicode61'
    )
    """,
    # FTS Trigram（原始规范化文本，精确子串）
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts_trigram USING fts5(
        chunk_id UNINDEXED,
        document_id UNINDEXED,
        heading,
        raw_text,
        tokenize = 'trigram'
    )
    """,
]


def init_schema(conn: sqlite3.Connection) -> None:
    """幂等初始化 schema 并登记 schema_version。"""
    try:
        with conn:
            for stmt in _SCHEMA_SQL:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO NOTHING",
                (SCHEMA_VERSION,),
            )
    except sqlite3.Error as exc:
        raise SqliteError(f"Schema 初始化失败: {exc}") from exc


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def check_fts_capability(conn: sqlite3.Connection | None = None) -> dict:
    """启动自检：确认 FTS5 与 trigram tokenizer 可用。

    能力由 SQLite 构建决定，与具体 db 文件无关，因此探针始终使用独立的
    in-memory 连接（不污染目标库，也兼容 query_only 只读连接）。
    conn 参数仅为兼容旧签名，会被忽略。
    """
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE _fts_probe USING fts5(a)")
        probe.execute("CREATE VIRTUAL TABLE _fts_probe_t USING fts5(a, tokenize='trigram')")
        probe.execute("INSERT INTO _fts_probe_t VALUES ('CoWoS-L 检查')")
        n = probe.execute("SELECT count(*) FROM _fts_probe_t WHERE _fts_probe_t MATCH '\"CoWoS-L\"'").fetchone()[0]
        return {"fts5": True, "trigram": n == 1}
    except sqlite3.Error as exc:
        raise SqliteError(f"FTS5 能力检查失败: {exc}") from exc
    finally:
        probe.close()
