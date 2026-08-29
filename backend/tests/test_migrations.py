"""M1-04/05 验收：clean init works, second init idempotent。"""

import sqlite3

from app.core.config import SCHEMA_VERSION
from app.storage.migrations import check_fts_capability, get_meta, init_schema, set_meta
from app.storage.sqlite import connect


def test_clean_init(tmp_path):
    conn = connect(tmp_path / "clean.db")
    init_schema(conn)
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"documents", "sections", "chunks", "indexing_jobs", "meta",
            "chunks_fts_terms", "chunks_fts_trigram", "document_tombstones"} <= tables
    assert get_meta(conn, "schema_version") == SCHEMA_VERSION
    conn.close()


def test_second_init_idempotent(tmp_path):
    path = tmp_path / "idem.db"
    conn = connect(path)
    init_schema(conn)
    init_schema(conn)  # 第二次不抛错、不破坏数据
    set_meta(conn, "schema_version", SCHEMA_VERSION)
    init_schema(conn)
    assert get_meta(conn, "schema_version") == SCHEMA_VERSION

    # 已有数据在重复 init 后保留
    conn.execute(
        "INSERT INTO documents (id, title, source_path, file_name, sha256) "
        "VALUES ('M01', '测试报告', 'D:/x/M01.md', 'M01.md', 'hash1')"
    )
    conn.commit()
    init_schema(conn)
    n = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    assert n == 1
    conn.close()


def test_wal_mode_enabled(tmp_path):
    conn = connect(tmp_path / "wal.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


def test_foreign_keys_enabled(tmp_path):
    conn = connect(tmp_path / "fk.db")
    v = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert v == 1
    conn.close()


def test_fts_capability_probe():
    conn = sqlite3.connect(":memory:")
    cap = check_fts_capability(conn)
    assert cap == {"fts5": True, "trigram": True}
    conn.close()
