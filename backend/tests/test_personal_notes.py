from __future__ import annotations

import sqlite3

from app.notes.store import NoteStore, ensure_notes_schema


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_notes_schema(conn)
    return conn


def test_create_list_filter_and_update() -> None:
    store = NoteStore(_conn())
    n = store.create(
        chunk_id="M04:ch1:0001",
        document_id="M04",
        heading_path="HBM4 > 接口",
        stance="mechanism",
        body="位宽约束来自通道数而不是单通道速率。",
    )
    assert n["id"].startswith("note_")
    assert store.list(chunk_id="M04:ch1:0001")[0]["body"].startswith("位宽")
    assert store.list(q="通道数")
    updated = store.update(n["id"], stance="agree")
    assert updated["stance"] == "agree"


def test_reject_empty_and_bad_stance() -> None:
    store = NoteStore(_conn())
    try:
        store.create(chunk_id="c", document_id="d", body="  ")
        raise AssertionError("empty body should fail")
    except ValueError:
        pass
    try:
        store.create(chunk_id="c", document_id="d", body="ok", stance="verified_fact")
        raise AssertionError("formal stance should fail")
    except ValueError:
        pass
