"""M1 测试 fixtures。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Config  # noqa: E402
from app.storage.migrations import init_schema  # noqa: E402
from app.storage.sqlite import connect  # noqa: E402


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Config:
    data_dir = tmp_path / "data"
    cfg = Config()
    cfg.paths.data_dir = str(data_dir)
    cfg.paths.log_dir = str(tmp_path / "logs")
    cfg.sqlite.path = str(data_dir / "catalog.db")
    return cfg


@pytest.fixture()
def db(tmp_path: Path):
    conn = connect(tmp_path / "test_catalog.db")
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def fixture_retrieval(tmp_path_factory):
    """P0-1 解耦：独立 fixture 语料（独立 Qdrant collection + 独立 SQLite）。

    基于 tests/fixtures 的确定性 10 篇语料构建，与 dev/prod 的生产 collection / catalog
    完全隔离，因此测试断言不受 KE_CONFIG（dev/prod）影响，可复现。
    返回 {cfg, engine, dense, conn, doc_ids}；DenseRetriever 复用独立 collection。
    """
    from pathlib import Path

    from app.chunking.semantic_chunker import SemanticChunker
    from app.core.config import ChunkingConfig, load_config
    from app.lexical.corpus import DEFAULT_FIXTURES, build_corpus_db
    from app.parser.markdown_parser import parse_markdown
    from app.retrieval.dense import DenseRetriever, build_section_records
    from app.retrieval.search_engine import SearchEngine

    fixtures = Path(__file__).resolve().parent / "fixtures"
    root = tmp_path_factory.mktemp("fixture_retrieval")

    cfg = load_config()
    cfg.qdrant.chunks_collection = "kb_chunks_fixtest"    # 独立测试 collection
    cfg.qdrant.sections_collection = "kb_sections_fixtest"

    conn, info = build_corpus_db(root / "corpus.db", DEFAULT_FIXTURES)  # 独立 sqlite
    dense = DenseRetriever(cfg)
    dense.ensure_collections()
    for col in (cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection):
        try:
            dense.store.client.delete_collection(col)
        except Exception:
            pass
    dense.ensure_collections()

    for name in DEFAULT_FIXTURES:
        doc_id = name.split("_")[0]
        doc = parse_markdown((fixtures / name).read_text(encoding="utf-8"))
        meta = {"domain": doc.metadata.get("domain", ""),
                "completed_at": doc.metadata.get("completed_at", "")}
        chunks = SemanticChunker(ChunkingConfig()).chunk_document(doc, doc_id)
        dense.index_chunks(chunks, {doc_id: meta})
        dense.index_sections(build_section_records(doc, doc_id))

    engine = SearchEngine(cfg, conn, dense)
    try:
        yield {"cfg": cfg, "engine": engine, "dense": dense,
               "conn": conn, "doc_ids": list(info["documents"])}
    finally:
        for col in (cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection):
            try:
                dense.store.client.delete_collection(col)
            except Exception:
                pass
        conn.close()
