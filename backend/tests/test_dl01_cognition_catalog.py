from pathlib import Path

from app.cognition.catalog_pipeline import CognitionCatalogPipeline
from app.cognition.scanner import scan as cognition_scan
from app.lexical.fts_search import LexicalSearcher
from app.storage.migrations import init_schema
from app.storage.sqlite import connect


QUESTION = """# 变压器约束

## 关键未知

变压器交付周期是否构成前置约束？标记词 COGLEX917。
"""

JUDGMENT = """# 资本效率判断

## 核心判断

CAPEX 扩张不等于回报改善。标记词 COGJUDGE42。
"""


def _env(tmp_config, tmp_path):
    root = tmp_path / "cognition"
    questions = root / "03_问题池"
    judgments = root / "04_判断台账"
    excluded = root / "01A_认知候选"
    questions.mkdir(parents=True)
    judgments.mkdir(parents=True)
    excluded.mkdir(parents=True)

    q = questions / "变压器问题.md"
    j = judgments / "资本效率.md"
    candidate = excluded / "候选.md"
    q.write_text(QUESTION, encoding="utf-8")
    j.write_text(JUDGMENT, encoding="utf-8")
    candidate.write_text("候选内容 CANDIDATE_ONLY，不得进入正式派生目录。", encoding="utf-8")

    tmp_config.cognition.root = str(root)
    tmp_config.cognition.include_dirs = ["03_问题池", "04_判断台账"]
    tmp_config.cognition.catalog_path = str(tmp_path / "catalog_cognition.db")
    conn = connect(tmp_config.cognition.catalog_path)
    init_schema(conn)
    pipeline = CognitionCatalogPipeline(tmp_config, conn)
    return root, q, j, candidate, conn, pipeline


def test_cognition_catalog_is_lexical_searchable_without_semantic_stack(tmp_config, tmp_path):
    root, q, j, candidate, conn, pipeline = _env(tmp_config, tmp_path)
    try:
        source_before = {
            p: (p.read_text(encoding="utf-8"), p.stat().st_mtime_ns)
            for p in (q, j, candidate)
        }

        result = cognition_scan(tmp_config, conn)
        stats = pipeline.apply_scan(result)

        assert stats["indexed"] == 2
        assert stats["errors"] == []
        assert stats["vector_pending"] == 2
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == conn.execute(
            "SELECT count(*) FROM chunks_fts_terms"
        ).fetchone()[0]
        assert conn.execute(
            "SELECT count(*) FROM documents WHERE source_path LIKE '%01A_认知候选%'"
        ).fetchone()[0] == 0

        hits = LexicalSearcher(conn).search_trigram("COGLEX917", k=10)
        assert hits
        assert all(hit.document_id.startswith("cog:") for hit in hits)
        assert any("变压器问题" in hit.document_id for hit in hits)

        for p, (text, mtime) in source_before.items():
            assert p.read_text(encoding="utf-8") == text
            assert p.stat().st_mtime_ns == mtime
    finally:
        conn.close()


def test_cognition_rename_preserves_manifest_id_and_later_modify_reuses_it(tmp_config, tmp_path):
    root, q, _j, _candidate, conn, pipeline = _env(tmp_config, tmp_path)
    try:
        pipeline.apply_scan(cognition_scan(tmp_config, conn))
        old_id = conn.execute(
            "SELECT id FROM documents WHERE source_path = ?", (str(q),)
        ).fetchone()["id"]

        renamed = q.with_name("变压器问题_重命名.md")
        q.rename(renamed)
        rename_scan = cognition_scan(tmp_config, conn)
        renamed_states = [s for s in rename_scan.states if s.status == "RENAMED"]
        assert len(renamed_states) == 1
        assert renamed_states[0].document_id == old_id
        stats = pipeline.apply_scan(rename_scan)
        assert stats["renamed"] == 1
        row = conn.execute("SELECT id, source_path FROM documents WHERE id = ?", (old_id,)).fetchone()
        assert row["source_path"] == str(renamed)

        renamed.write_text(
            QUESTION.replace("COGLEX917", "COGLEX918"), encoding="utf-8"
        )
        modify_scan = cognition_scan(tmp_config, conn)
        modified = [s for s in modify_scan.states if s.status == "MODIFIED"]
        assert len(modified) == 1
        assert modified[0].document_id == old_id
        stats2 = pipeline.apply_scan(modify_scan)
        assert stats2["indexed"] == 1
        assert conn.execute("SELECT count(*) FROM documents WHERE id = ?", (old_id,)).fetchone()[0] == 1
        assert LexicalSearcher(conn).search_trigram("COGLEX918", k=10)
        assert not LexicalSearcher(conn).search_trigram("COGLEX917", k=10)
        pending_ids = {item["document_id"] for item in pipeline.pending_vector_sync()}
        assert old_id in pending_ids
    finally:
        conn.close()


def test_cognition_delete_is_local_and_records_vector_delete(tmp_config, tmp_path):
    _root, q, _j, _candidate, conn, pipeline = _env(tmp_config, tmp_path)
    try:
        pipeline.apply_scan(cognition_scan(tmp_config, conn))
        doc_id = conn.execute(
            "SELECT id FROM documents WHERE source_path = ?", (str(q),)
        ).fetchone()["id"]

        q.unlink()
        stats = pipeline.apply_scan(cognition_scan(tmp_config, conn))

        assert stats["deleted"] == 1
        assert conn.execute("SELECT count(*) FROM documents WHERE id = ?", (doc_id,)).fetchone()[0] == 0
        pending = {item["document_id"]: item for item in pipeline.pending_vector_sync()}
        assert pending[doc_id]["operation"] == "delete"
    finally:
        conn.close()
