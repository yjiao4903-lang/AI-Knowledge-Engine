"""M3 验收：M04 真实报告 fixture 分块 + 六项硬性 Gate（Addendum §11-14）。"""

import pytest

from app.chunking.qa import compute_stats, validate_chunks
from app.chunking.semantic_chunker import SemanticChunker
from app.core.config import ChunkingConfig
from app.parser.markdown_parser import parse_markdown

from pathlib import Path

M04_PATH = Path(__file__).parent / "fixtures" / "M04_sample.md"


@pytest.fixture(scope="module")
def m04():
    text = M04_PATH.read_text(encoding="utf-8")
    doc = parse_markdown(text)
    chunks = SemanticChunker(ChunkingConfig()).chunk_document(doc, "M04")
    return doc, chunks, len(text.splitlines())


def test_m04_gate(m04):
    doc, chunks, line_count = m04
    v = validate_chunks(chunks, doc, line_count)
    assert v["gate_passed"], f"Gate 未通过: {v}"


def test_m04_chunk_quality(m04):
    doc, chunks, _ = m04
    assert len(chunks) > 30
    # 技术词进入 plain_text
    all_plain = "\n".join(c.plain_text for c in chunks)
    for term in ("HBM4", "CoWoS-L", "High-NA", "MR-MUF"):
        assert term in all_plain, f"技术词 {term} 丢失"
    # embedding_text 均带文档上下文
    assert all(c.embedding_text.startswith("Document: ") for c in chunks)
    # heading_path 正确（含文档标题根）
    assert all("【旗舰战略研究报告】" in c.heading_path for c in chunks)


def test_m04_stats_shape(m04):
    doc, chunks, _ = m04
    stats = compute_stats(chunks)
    d = stats["length_distribution"]
    assert d["min"] <= d["p50"] <= d["max"]
    assert stats["content_types"]
    # 表格/因果图/公式有独立类型
    ct = stats["content_types"]
    assert ct.get("table", 0) + ct.get("monitoring", 0) + ct.get("comparison", 0) >= 4
    assert ct.get("causal_chain", 0) >= 10  # 12 个 ASCII 拓扑图
