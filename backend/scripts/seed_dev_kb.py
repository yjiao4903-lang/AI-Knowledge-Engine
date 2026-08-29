"""M10 开发语料库 seed：把 10 篇 fixture 复制到 data/dev_kb，
并用真实 catalog（data/catalog.db）+ kb_chunks_v1 全量索引。

生产化切换：把 config.yaml 的 knowledge_base.roots 指向真实归档后运行
  python backend/scripts/reindex.py scan
（全量索引耗时与语料规模成正比，属数据规模操作）。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.indexing.pipeline import EmbedderAdapter, IndexPipeline  # noqa: E402
from app.inference.manager import InferenceManager  # noqa: E402
from app.storage.migrations import init_schema  # noqa: E402
from app.storage.sqlite import connect  # noqa: E402


def main() -> int:
    cfg = load_config()
    dev_kb = Path(PROJECT_ROOT / "data" / "dev_kb")
    dev_kb.mkdir(parents=True, exist_ok=True)

    fixtures = sorted((PROJECT_ROOT / "backend" / "tests" / "fixtures").glob("M*_sample.md"))
    for f in fixtures:
        shutil.copy(f, dev_kb / f.name)
    cfg.knowledge_base.roots = [str(dev_kb)]
    print(f"dev_kb: {len(fixtures)} reports")

    # 清空旧 catalog（dev 环境可重建）
    db_path = Path(cfg.sqlite.path)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    conn = connect(db_path)
    init_schema(conn)
    mgr = InferenceManager(cfg)
    try:
        pipeline = IndexPipeline(cfg, conn, EmbedderAdapter(cfg, mgr))
        # 重建 Qdrant collections
        for col in (cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection):
            try:
                pipeline.qdrant_client().delete_collection(col)
            except Exception:
                pass
        from app.storage.qdrant import QdrantStore

        QdrantStore(cfg.qdrant).ensure_collections()

        from app.indexing.scanner import scan
        from app.parser.markdown_parser import parse_markdown
        from app.retrieval.dense import DenseRetriever, build_section_records

        result = scan(cfg, conn)
        print("states:", {s: len(result.by_status(s)) for s in
                          ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")})
        stats = pipeline.apply_scan(result)
        print(f"indexed={stats['indexed']} errors={stats['errors']}")

        # 重建 sections 向量（apply_scan/index_file 只覆盖 chunks）
        dense = DenseRetriever(cfg)
        total_sections = 0
        for f in fixtures:
            doc_id = f.stem.split("_")[0]
            doc = parse_markdown(f.read_text(encoding="utf-8"))
            records = build_section_records(doc, doc_id)
            r = dense.index_sections(records)
            total_sections += r["sections"]
        print(f"sections total: {total_sections}")
        return 0 if not stats["errors"] else 1
    finally:
        mgr.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
