"""Chunk 质量统计与硬性验收（M3，Addendum §11-14）。

Gate：Broken Table / Broken Formula / Cross-section / Invalid Line Range /
Duplicate Chunk ID / Empty Chunk 全部为 0 才算 M3 通过。
"""

from __future__ import annotations

from collections import Counter

from app.chunking.chunk_models import Chunk
from app.parser.models import Block, ParsedDocument


def _percentile(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    idx = min(int(len(sorted_vals) * p), len(sorted_vals) - 1)
    return sorted_vals[idx]


def compute_stats(chunks: list[Chunk]) -> dict:
    lengths = sorted(c.char_len for c in chunks)
    return {
        "chunk_count": len(chunks),
        "length_distribution": {
            "min": lengths[0] if lengths else 0,
            "p25": _percentile(lengths, 0.25),
            "p50": _percentile(lengths, 0.50),
            "p75": _percentile(lengths, 0.75),
            "p90": _percentile(lengths, 0.90),
            "p95": _percentile(lengths, 0.95),
            "max": lengths[-1] if lengths else 0,
            "mean": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        },
        "content_types": dict(Counter(c.content_type for c in chunks)),
        "oversized": sum(1 for c in chunks if c.oversized),
    }


def validate_chunks(chunks: list[Chunk], doc: ParsedDocument, doc_line_count: int) -> dict:
    """六项硬性 Gate 校验。"""
    # special blocks 必须完整落在某一个 chunk 内（未断表/未断公式）
    special = [
        b for s in doc.sections for b in s.blocks if b.block_type in ("table", "formula", "mermaid", "ascii_diagram")
    ]
    broken_table = 0
    broken_formula = 0
    for b in special:
        contained = [
            c for c in chunks if c.start_line <= b.start_line and c.end_line >= b.end_line
        ]
        ok = len(contained) >= 1
        if not ok:
            if b.block_type == "table":
                broken_table += 1
            elif b.block_type == "formula":
                broken_formula += 1

    # 跨 Section：chunk 区间内不得包含其他 section 的标题行
    heading_lines: dict[int, str] = {}
    for s in doc.sections:
        heading_lines[s.start_line] = s.section_id
    cross_section = 0
    for c in chunks:
        own = c.section_id
        for line, sid in heading_lines.items():
            if c.start_line <= line <= c.end_line and sid != own:
                cross_section += 1
                break

    invalid_line_range = sum(
        1 for c in chunks
        if c.start_line < 1 or c.end_line > doc_line_count or c.start_line > c.end_line
    )
    ids = [c.chunk_id for c in chunks]
    duplicate_ids = len(ids) - len(set(ids))
    empty_chunks = sum(1 for c in chunks if not c.plain_text.strip())

    return {
        "broken_table": broken_table,
        "broken_formula": broken_formula,
        "cross_section": cross_section,
        "invalid_line_range": invalid_line_range,
        "duplicate_chunk_id": duplicate_ids,
        "empty_chunk": empty_chunks,
        "gate_passed": not (broken_table or broken_formula or cross_section
                            or invalid_line_range or duplicate_ids or empty_chunks),
    }
