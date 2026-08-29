"""评测语料构建（M4+）：fixtures -> parse -> chunk -> SQLite(+FTS)。

供 m4_eval.py 与 pytest 集成测试共用。只读 fixtures，不触碰知识源目录。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.chunking.semantic_chunker import SemanticChunker
from app.core.config import ChunkingConfig
from app.parser.markdown_parser import parse_markdown
from app.storage.migrations import init_schema
from app.storage.repositories.knowledge import (
    ChunkRepository,
    DocumentRepository,
    SectionRepository,
)
from app.storage.sqlite import connect

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures"
# M9 Golden 语料：10 篇跨领域报告
DEFAULT_FIXTURES = [
    "M04_sample.md", "M05_sample.md", "M06_sample.md", "M07_sample.md",
    "M09_sample.md", "M10_sample.md", "M14_sample.md", "M16_sample.md",
    "M18_sample.md", "M22_sample.md",
]


def build_corpus_db(db_path: str | Path, fixture_names: list[str] | None = None) -> tuple[sqlite3.Connection, dict]:
    """构建语料库。返回 (conn, info)。

    info: {doc_id: {"chunks": n, "file": name}}, 以及总计。
    """
    conn = connect(db_path)
    init_schema(conn)
    chunker = SemanticChunker(ChunkingConfig())
    doc_repo = DocumentRepository(conn)
    sec_repo = SectionRepository(conn)
    chunk_repo = ChunkRepository(conn)

    info: dict = {"documents": {}}
    total_chunks = 0
    for name in (fixture_names or DEFAULT_FIXTURES):
        path = FIXTURES_DIR / name
        text = path.read_text(encoding="utf-8")
        doc = parse_markdown(text)
        doc_id = doc.metadata.get("report_code") or path.stem.split("_")[0]
        chunks = chunker.chunk_document(doc, doc_id)

        doc_repo.upsert({
            "id": doc_id,
            "title": doc.metadata.get("title", doc.title),
            "domain": doc.metadata.get("domain", ""),
            "status": doc.metadata.get("status", ""),
            "source_path": str(path),
            "file_name": path.name,
            "sha256": f"fixture-{doc_id}",
            "parser_version": "0.1.0",
            "chunker_version": chunker.chunker_version,
            "schema_version": "1.0.0",
        })
        sec_repo.replace_for_document([
            {
                "id": f"{doc_id}:{s.section_id}", "document_id": doc_id,
                "parent_section_id": f"{doc_id}:{s.parent_id}" if s.parent_id else None,
                "level": s.level, "heading": s.heading,
                "heading_path": " > ".join(s.heading_path), "section_type": s.section_type,
                "ordinal": s.ordinal, "start_line": s.start_line, "end_line": s.end_line,
            }
            for s in doc.sections
        ])
        # chunks：补 section_id 外键（chunk.section_id 无 doc 前缀，DB 中 sections 带前缀）
        db_chunks = []
        for c in chunks:
            d = c.to_db_dict()
            d["section_id"] = f"{doc_id}:{c.section_id}"
            db_chunks.append(d)
        with conn:
            chunk_repo.upsert_batch(db_chunks)
        info["documents"][doc_id] = {"chunks": len(chunks), "file": name}
        total_chunks += len(chunks)

    info["total_chunks"] = total_chunks
    return conn, info
