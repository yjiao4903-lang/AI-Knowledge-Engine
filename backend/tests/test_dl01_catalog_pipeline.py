from pathlib import Path

from app.indexing.catalog_pipeline import CatalogIndexPipeline
from app.lexical.fts_search import LexicalSearcher


def _write_report(path: Path, *, fact: str) -> None:
    path.write_text(
        """---
report_code: DL01_TEST
title: DL-01 Catalog Test
domain: semiconductors
---
# DL-01 Catalog Test

## Memory bandwidth

{fact}
""".format(fact=fact),
        encoding="utf-8",
    )


def test_catalog_index_is_searchable_without_vector_sync(tmp_config, db, tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = reports / "dl01_test.md"
    _write_report(report, fact="HBM4 provides a deterministic lexical anchor ALPHABW42.")
    tmp_config.knowledge_base.roots = [str(reports)]

    pipeline = CatalogIndexPipeline(tmp_config, db)
    result = pipeline.index_file(report)

    assert result["document_id"] == "DL01_TEST"
    assert result["vector_status"] == "pending"
    assert result["chunks"] > 0
    assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == result["chunks"]
    assert db.execute("SELECT count(*) FROM chunks_fts_terms").fetchone()[0] == result["chunks"]
    assert db.execute("SELECT count(*) FROM chunks_fts_trigram").fetchone()[0] == result["chunks"]

    hits = LexicalSearcher(db).search_trigram("ALPHABW42", k=10)
    assert any(hit.document_id == "DL01_TEST" for hit in hits)

    pending = pipeline.pending_vector_sync()
    assert len(pending) == 1
    assert pending[0]["document_id"] == "DL01_TEST"
    assert pending[0]["operation"] == "upsert"


def test_catalog_reindex_replaces_fts_before_vector_sync(tmp_config, db, tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = reports / "dl01_test.md"
    tmp_config.knowledge_base.roots = [str(reports)]
    pipeline = CatalogIndexPipeline(tmp_config, db)

    _write_report(report, fact="The first lexical marker is OLDMARKER77.")
    pipeline.index_file(report)
    assert LexicalSearcher(db).search_trigram("OLDMARKER77", k=10)

    _write_report(report, fact="The replacement lexical marker is NEWMARKER88.")
    pipeline.index_file(report, doc_id="DL01_TEST")

    assert not LexicalSearcher(db).search_trigram("OLDMARKER77", k=10)
    assert LexicalSearcher(db).search_trigram("NEWMARKER88", k=10)
    pending = pipeline.pending_vector_sync()
    assert [item["document_id"] for item in pending] == ["DL01_TEST"]


def test_catalog_delete_keeps_explicit_vector_delete_marker(tmp_config, db, tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = reports / "dl01_test.md"
    _write_report(report, fact="Deletion marker DELETEANCHOR55.")
    tmp_config.knowledge_base.roots = [str(reports)]
    pipeline = CatalogIndexPipeline(tmp_config, db)
    pipeline.index_file(report)

    pipeline.remove_document("DL01_TEST", str(report))

    assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
    assert not LexicalSearcher(db).search_trigram("DELETEANCHOR55", k=10)
    pending = pipeline.pending_vector_sync()
    assert len(pending) == 1
    assert pending[0]["document_id"] == "DL01_TEST"
    assert pending[0]["operation"] == "delete"


def test_clear_vector_pending_is_idempotent(tmp_config, db, tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = reports / "dl01_test.md"
    _write_report(report, fact="Explicit vector maintenance marker.")
    pipeline = CatalogIndexPipeline(tmp_config, db)
    pipeline.index_file(report)

    pipeline.clear_vector_pending("DL01_TEST")
    pipeline.clear_vector_pending("DL01_TEST")

    assert pipeline.pending_vector_sync() == []
