"""M5 索引脚本：5 篇 fixture 语料 -> Embedding -> Qdrant（kb_chunks_v1 / kb_sections_v1）。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.chunking.semantic_chunker import SemanticChunker  # noqa: E402
from app.core.config import ChunkingConfig, load_config  # noqa: E402
from app.lexical.corpus import build_corpus_db  # noqa: E402
from app.parser.markdown_parser import parse_markdown  # noqa: E402
from app.retrieval.dense import DenseRetriever, build_section_records  # noqa: E402


def main() -> int:
    cfg = load_config()
    import tempfile

    # SQLite catalog 建在临时目录（真实 catalog 属于 M8 管线；此处只为向量索引供料）
    tmp = Path(tempfile.mkdtemp())
    conn, info = build_corpus_db(tmp / "corpus.db")
    print(f"corpus: {info['total_chunks']} chunks from {len(info['documents'])} docs")

    retriever = DenseRetriever(cfg)
    print(f"device: {retriever.device} ({retriever.device_reason})")
    retriever.ensure_collections()

    # 重建索引：清空两个 collection（fixture 语料重建成本低）
    for col in (cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection):
        retriever.store.client.delete_collection(col)
    retriever.ensure_collections()

    total = {"chunks": 0, "sections": 0, "embed_ms": 0.0}
    for name in ("M04_sample.md", "M06_sample.md", "M09_sample.md", "M14_sample.md", "M18_sample.md"):
        doc_id = name.split("_")[0]
        doc = parse_markdown((PROJECT_ROOT / "backend" / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
        chunks = SemanticChunker(ChunkingConfig()).chunk_document(doc, doc_id)
        meta = {"domain": doc.metadata.get("domain", ""), "completed_at": doc.metadata.get("completed_at", "")}
        r1 = retriever.index_chunks(chunks, {doc_id: meta})
        sections = build_section_records(doc, doc_id)
        r2 = retriever.index_sections(sections)
        total["chunks"] += r1["chunks"]
        total["sections"] += r2["sections"]
        total["embed_ms"] += r1["embed_ms"] + r2["embed_ms"]
        print(f"{doc_id}: chunks={r1['chunks']} sections={r2['sections']} embed={r1['embed_ms'] + r2['embed_ms']}ms")

    cinfo = retriever.store.collection_info(cfg.qdrant.chunks_collection)
    sinfo = retriever.store.collection_info(cfg.qdrant.sections_collection)
    print(f"qdrant: kb_chunks_v1={cinfo} kb_sections_v1={sinfo}")
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
