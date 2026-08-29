"""Chunk 数据模型（M3）。

每个 Chunk 保存三种文本（raw_markdown / plain_text / embedding_text）、
稳定 chunk_id、行号区间与证据等级继承。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

CHUNKER_VERSION = "0.3.0"


@dataclass
class Chunk:
    chunk_id: str  # {document_id}:{section_id}:{ordinal:04d}
    document_id: str
    section_id: str
    ordinal: int  # 文档内全局序号，1 起
    heading_path: str  # " > " 连接
    content_type: str
    raw_markdown: str
    plain_text: str
    embedding_text: str
    lexical_text: str  # 分词后词项串（M4），供 FTS terms 索引
    start_line: int
    end_line: int
    evidence_level: int | None = None
    evidence_levels: list[int] = field(default_factory=list)
    oversized: bool = False

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.raw_markdown.encode("utf-8")).hexdigest()

    @property
    def char_len(self) -> int:
        return len(self.plain_text)

    def to_db_dict(self) -> dict:
        """转换为 ChunkRepository.upsert_batch 所需 dict。"""
        import json

        return {
            "id": self.chunk_id,
            "document_id": self.document_id,
            "section_id": self.section_id,
            "ordinal": self.ordinal,
            "heading_path": self.heading_path,
            "content_type": self.content_type,
            "raw_markdown": self.raw_markdown,
            "plain_text": self.plain_text,
            "embedding_text": self.embedding_text,
            "lexical_text": self.lexical_text,
            "evidence_level": self.evidence_level,
            "evidence_levels_json": json.dumps(self.evidence_levels) if self.evidence_levels else None,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content_hash": self.content_hash,
        }


def build_chunk_id(document_id: str, section_id: str, ordinal: int) -> str:
    return f"{document_id}:{section_id}:{ordinal:04d}"
