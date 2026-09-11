"""P8-ENG-01：reconcile 确定性回归。

复现（修复前）：
1. 库内已索引 M09（Transformer 专题）。
2. 磁盘新增一个同 report_code、不同内容的 M09 文件（男女身体构造差异）。
3. ``build_index_plan`` 只按本批候选分组，把裸 id ``M09`` 分配给新文件；
   ``index_file`` 随即 ``DELETE FROM chunks WHERE document_id='M09'`` 并替换
   documents 行 -> 既有文档被静默覆盖。下一次 reconcile 又把旧文件当 NEW
   写回，M09 chunk 数在 45↔77 之间抖动，legacy 金标间歇 ``unresolved``。

本测试用真实 ``scan`` + ``CatalogIndexPipeline.apply_scan``（model-free，
不触碰 Qdrant/模型）验证：既有 M09 不被覆盖、新文件 sha8 消歧、重复 reconcile 幂等。
"""

from pathlib import Path

from app.indexing.catalog_pipeline import CatalogIndexPipeline
from app.indexing.scanner import scan


def _write_report(path: Path, code: str, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(
        f"## Section {i}\n\n{marker} paragraph {i} " + "研究内容 " * 20
        for i in range(1, 4)
    )
    path.write_text(
        f"---\nreport_code: {code}\ntitle: {marker}\n---\n# {marker}\n\n{body}\n",
        encoding="utf-8",
    )


def _write_plain(path: Path, marker: str) -> None:
    """无 front matter / report_code 的成品报告：doc_id 落回 stem。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(f"## Section {i}\n\n{marker} paragraph {i} " + "研究内容 " * 20
                       for i in range(1, 4))
    path.write_text(f"# {marker}\n\n{body}\n", encoding="utf-8")


def _chunks(db, doc_id: str) -> int:
    return db.execute(
        "SELECT count(*) FROM chunks WHERE document_id = ?", (doc_id,)).fetchone()[0]


def _source_path(db, doc_id: str) -> str:
    return db.execute(
        "SELECT source_path FROM documents WHERE id = ?", (doc_id,)).fetchone()["source_path"]


def test_m09_same_code_different_content_keeps_existing_document(tmp_config, db, tmp_path):
    reports = tmp_path / "reports"
    old = reports / "M09_Transformer" / "M09_Transformer_最终报告.md"
    new = reports / "M09_男女身体构造差异" / "M09_男女身体构造差异_最终报告.md"
    _write_report(old, "M09_TEST", "TRANSFORMER")

    tmp_config.knowledge_base.roots = [str(reports)]
    tmp_config.knowledge_base.extensions = [".md"]
    pipeline = CatalogIndexPipeline(tmp_config, db)

    first = pipeline.apply_scan(scan(tmp_config, db))
    assert first["indexed"] == 1 and first["errors"] == []
    base_chunks = _chunks(db, "M09")
    assert base_chunks > 0
    assert _source_path(db, "M09") == str(old)

    # 新增同 code、不同内容文件：不得覆盖既有 M09
    _write_report(new, "M09_TEST", "GENDER-DIFFERENCE")
    second = pipeline.apply_scan(scan(tmp_config, db))
    assert second["errors"] == []
    assert _source_path(db, "M09") == str(old)
    assert _chunks(db, "M09") == base_chunks

    new_ids = [r["id"] for r in db.execute(
        "SELECT id FROM documents WHERE id LIKE 'M09__%'").fetchall()]
    assert len(new_ids) == 1
    assert _chunks(db, new_ids[0]) > 0
    assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 2

    # 重复 reconcile 必须幂等：无写入、无删除、身份与计数不变
    third = pipeline.apply_scan(scan(tmp_config, db))
    assert third["indexed"] == 0 and third["deleted"] == 0 and third["errors"] == []
    assert _source_path(db, "M09") == str(old)
    assert _chunks(db, "M09") == base_chunks
    assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 2


def test_generic_final_report_id_does_not_overwrite(tmp_config, db, tmp_path):
    """通用 stem ``_最终报告`` 落回 stem 作 doc_id，多主题同名时不得互相覆盖。"""
    reports = tmp_path / "reports"
    a = reports / "A_主题" / "_最终报告.md"
    b = reports / "B_主题" / "_最终报告.md"
    _write_plain(a, "TOPIC-A")

    tmp_config.knowledge_base.roots = [str(reports)]
    tmp_config.knowledge_base.extensions = [".md"]
    pipeline = CatalogIndexPipeline(tmp_config, db)

    # 先只索引 A（B 不存在）
    pipeline.apply_scan(scan(tmp_config, db))
    assert _source_path(db, "_最终报告") == str(a)

    # 再加入 B：必须 sha8 消歧，A 不被覆盖
    _write_plain(b, "TOPIC-B")
    pipeline.apply_scan(scan(tmp_config, db))
    assert _source_path(db, "_最终报告") == str(a)
    disambiguated = [r["id"] for r in db.execute(
        "SELECT id FROM documents WHERE id LIKE '_最终报告__%'").fetchall()]
    assert len(disambiguated) == 1
