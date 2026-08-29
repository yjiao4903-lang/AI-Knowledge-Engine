"""M3 验收统计：M04 fixture 分块统计 + 人工抽样输出（Addendum §11-13）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.chunking.qa import compute_stats, validate_chunks  # noqa: E402
from app.chunking.semantic_chunker import SemanticChunker  # noqa: E402
from app.core.config import ChunkingConfig  # noqa: E402
from app.parser.markdown_parser import parse_markdown  # noqa: E402

M04 = PROJECT_ROOT / "backend" / "tests" / "fixtures" / "M04_sample.md"


def main() -> None:
    text = M04.read_text(encoding="utf-8")
    doc = parse_markdown(text)
    chunks = SemanticChunker(ChunkingConfig()).chunk_document(doc, "M04")
    stats = compute_stats(chunks)
    gate = validate_chunks(chunks, doc, len(text.splitlines()))

    print(json.dumps({"stats": stats, "gate": gate}, ensure_ascii=False, indent=2))

    # 人工抽样：按类型抽取，写入 data/m3_sample_review.md
    by_type: dict[str, list] = {}
    for c in chunks:
        by_type.setdefault(c.content_type, []).append(c)
    picks: list[tuple[str, object]] = []
    for t, n in (("prose", 10), ("table", 5), ("formula", 3), ("causal_chain", 3),
                 ("monitoring", 3), ("reference", 3), ("audit", 3), ("summary", 2)):
        for c in by_type.get(t, [])[:n]:
            picks.append((t, c))

    lines = ["# M3 人工抽样评审（M04）", ""]
    seen = set()
    for t, c in picks:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        lines += [
            f"## [{t}] {c.chunk_id}",
            f"- section: {c.section_id} | lines: {c.start_line}-{c.end_line} | "
            f"evidence: L{c.evidence_level} ({c.evidence_levels}) | chars: {c.char_len} | oversized: {c.oversized}",
            f"- heading_path: {c.heading_path}",
            "", "```markdown", c.raw_markdown, "```", "",
        ]
    out = PROJECT_ROOT / "data" / "m3_sample_review.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nsample review written: {out} ({len(seen)} chunks)")


if __name__ == "__main__":
    main()
