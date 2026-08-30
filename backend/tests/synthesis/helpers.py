"""Synthesis 测试辅助：在临时 SQLite 中种入 document/section/chunk 供 grounding 用。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))


def seed_doc(conn, doc_id: str = "M04", title: str = "半导体先进封装 HBM4") -> str:
    from app.storage.repositories.knowledge import DocumentRepository

    doc = {
        "id": doc_id,
        "report_code": doc_id,
        "title": title,
        "source_path": f"tests/{doc_id}.md",
        "file_name": f"{doc_id}.md",
        "sha256": "0" * 64,
        "domain": "semiconductor",
        "status": "final",
    }
    DocumentRepository(conn).upsert(doc)
    conn.execute(
        "INSERT INTO sections (id, document_id, level, heading, heading_path, "
        "start_line, end_line) VALUES (?,?,?,?,?,?,?)",
        (f"{doc_id}:ch1", doc_id, 2, "HBM4 接口", f"ch1 > {doc_id}:ch1", 1, 20),
    )
    return doc_id


def seed_chunk(conn, chunk_id: str, text: str, *, doc_id: str = "M04", heading: str = "HBM4 接口") -> str:
    """插入一个 chunk，返回其 content_hash。"""
    from app.storage.repositories.knowledge import ChunkRepository

    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    section_id = f"{doc_id}:ch1"
    conn.execute(
        "INSERT OR IGNORE INTO sections (id, document_id, level, heading, heading_path, "
        "start_line, end_line) VALUES (?,?,?,?,?,?,?)",
        (section_id, doc_id, 2, "HBM4 接口", heading, 1, 20),
    )
    chunk = {
        "id": chunk_id,
        "document_id": doc_id,
        "section_id": section_id,
        "ordinal": 1,
        "heading_path": heading,
        "content_type": "prose",
        "raw_markdown": text,
        "plain_text": text,
        "embedding_text": text,
        "lexical_text": text,
        "evidence_level": 2,
        "start_line": 1,
        "end_line": 20,
        "content_hash": h,
    }
    ChunkRepository(conn).upsert_batch([chunk])
    return h