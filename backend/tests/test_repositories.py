"""M1-08 Repository 层测试（含 FTS 同步、FTS 语法引号规则）。"""

import json
import time

from app.storage.repositories.knowledge import (
    ChunkRepository,
    DocumentRepository,
    IndexJobRepository,
    SectionRepository,
)

DOC = {
    "id": "M04",
    "report_code": "M04",
    "title": "后摩尔时代半导体全景",
    "domain": "Domain II",
    "status": "final",
    "source_path": "D:/AI深度报告归档/旗舰战略专题报告_M04.md",
    "file_name": "旗舰战略专题报告_M04.md",
    "file_size": 123456,
    "file_mtime_ns": 1700000000000000000,
    "sha256": "abc123",
    "parser_version": "0.1.0",
    "chunker_version": "0.1.0",
    "schema_version": "1.0.0",
}

SECTION = {
    "id": "M04:ch3-2",
    "document_id": "M04",
    "parent_section_id": "M04:ch3",
    "level": 2,
    "heading": "3.2 HBM代际演进",
    "heading_path": "第3章 > 3.2 HBM代际演进",
    "section_type": "body",
    "ordinal": 1,
    "start_line": 100,
    "end_line": 200,
}

CHUNK = {
    "id": "M04:ch3-2:0001",
    "document_id": "M04",
    "section_id": "M04:ch3-2",
    "ordinal": 1,
    "heading_path": "第3章 > 3.2 HBM代际演进",
    "content_type": "prose",
    "raw_markdown": "HBM4 将接口位宽从 1024-bit 提升至 2048-bit。",
    "plain_text": "HBM4 将接口位宽从 1024-bit 提升至 2048-bit。",
    "embedding_text": "Document: ...\nHBM4 将接口位宽从 1024-bit 提升至 2048-bit。",
    "lexical_text": "HBM4 接口 位宽 提升 2048-bit",
    "evidence_level": 1,
    "evidence_levels_json": json.dumps([1]),
    "content_hash": "h1",
    "start_line": 100,
    "end_line": 110,
}


def test_document_upsert_get(db):
    repo = DocumentRepository(db)
    repo.upsert(DOC)
    doc = repo.get("M04")
    assert doc["title"] == DOC["title"]
    assert repo.get_by_source_path(DOC["source_path"])["id"] == "M04"

    # 更新（同 id）幂等
    DOC2 = {**DOC, "title": "更新后的标题", "sha256": "def456"}
    repo.upsert(DOC2)
    assert repo.get("M04")["title"] == "更新后的标题"
    assert repo.get("M04")["sha256"] == "def456"


def test_document_source_path_unique(db):
    from app.core.errors import SqliteError

    repo = DocumentRepository(db)
    repo.upsert(DOC)
    dup = {**DOC, "id": "M04B"}
    try:
        repo.upsert(dup)
        assert False, "unique(source_path) 应触发 SqliteError"
    except SqliteError:
        pass


def test_sections_replace(db):
    DocumentRepository(db).upsert(DOC)
    srepo = SectionRepository(db)
    srepo.replace_for_document([SECTION])
    sections = srepo.list_for_document("M04")
    assert len(sections) == 1 and sections[0]["heading"] == "3.2 HBM代际演进"


def test_chunks_upsert_and_fts(db):
    DocumentRepository(db).upsert(DOC)
    SectionRepository(db).replace_for_document([SECTION])
    crepo = ChunkRepository(db)
    n = crepo.upsert_batch([CHUNK])
    assert n == 1
    assert crepo.count() == 1

    # FTS terms：分词后词项可检索
    rows = db.execute(
        "SELECT chunk_id FROM chunks_fts_terms WHERE chunks_fts_terms MATCH 'HBM4'"
    ).fetchall()
    assert [r["chunk_id"] for r in rows] == [CHUNK["id"]]

    # FTS trigram：精确子串，含 - 必须双引号（FTS5 语法）
    rows = db.execute(
        "SELECT chunk_id FROM chunks_fts_trigram WHERE chunks_fts_trigram MATCH '\"2048-bit\"'"
    ).fetchall()
    assert [r["chunk_id"] for r in rows] == [CHUNK["id"]]

    # 重复 upsert 同 chunk 不产生 FTS 重复行
    crepo.upsert_batch([{**CHUNK, "content_hash": "h2"}])
    n = db.execute(
        "SELECT count(*) FROM chunks_fts_terms WHERE chunk_id = ?", (CHUNK["id"],)
    ).fetchone()[0]
    assert n == 1


def test_document_delete_cascades_fts(db):
    DocumentRepository(db).upsert(DOC)
    SectionRepository(db).replace_for_document([SECTION])
    crepo = ChunkRepository(db)
    crepo.upsert_batch([CHUNK])

    DocumentRepository(db).delete("M04")
    assert crepo.count() == 0
    assert db.execute("SELECT count(*) FROM chunks_fts_terms").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM chunks_fts_trigram").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM sections").fetchone()[0] == 0


def test_indexing_job_lifecycle(db):
    jrepo = IndexJobRepository(db)
    jrepo.create("job-1", started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    jrepo.finish(
        "job-1",
        finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        status="success",
        files_seen=3,
        files_changed=1,
        chunks_upserted=42,
    )
    row = dict(db.execute("SELECT * FROM indexing_jobs WHERE id='job-1'").fetchone())
    assert row["status"] == "success" and row["chunks_upserted"] == 42
