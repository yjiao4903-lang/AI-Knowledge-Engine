"""M5 集成测试：Qdrant Dense 索引/检索/Metadata Filter（spec §25-32）。

前置：Qdrant 运行中 + scripts/m5_index.py 已索引（或用例内索引）。
"""

import pytest

from app.core.config import load_config
from app.retrieval.dense import DenseRetriever


def _retriever_available() -> DenseRetriever | None:
    try:
        r = DenseRetriever(load_config())
        info = r.store.client.get_collections()
        names = {c.name for c in info.collections}
        if r.cfg.qdrant.chunks_collection not in names:
            return None
        points = r.store.collection_info(r.cfg.qdrant.chunks_collection)["points_count"]
        if not points:
            return None
        return r
    except Exception:
        return None


@pytest.fixture(scope="module")
def retriever():
    r = _retriever_available()
    if r is None:
        pytest.skip("Qdrant 无索引（先运行 backend/scripts/m5_index.py）")
    return r


def test_search_returns_payload_and_scores(retriever):
    hits, embed_ms = retriever.search("HBM4 的接口位宽是多少？", k=5)
    assert len(hits) == 5
    for h in hits:
        p = h["payload"]
        assert {"chunk_id", "document_id", "section_id", "content_type", "evidence_level", "domain"} <= set(p)
        assert h["score"] > 0
    assert embed_ms >= 0
    # Top1 应为 M04 的 HBM 相关 chunk
    assert hits[0]["payload"]["document_id"] == "M04"


def test_exact_query_top(retriever):
    hits, _ = retriever.search("EXE:5000 的成本和吞吐问题", k=3)
    assert all(h["payload"]["document_id"] == "M04" for h in hits)


def test_metadata_filter_evidence_level(retriever):
    hits_all, _ = retriever.search("先进封装", k=20)
    hits_l1, _ = retriever.search("先进封装", k=20, filters={"evidence_levels": [1]})
    assert hits_all and hits_l1
    assert all(h["payload"]["evidence_level"] == 1 for h in hits_l1)
    assert len(hits_l1) <= len(hits_all)


def test_metadata_filter_document(retriever):
    hits, _ = retriever.search("数据中心 算力", k=20, filters={"document_ids": ["M06"]})
    assert hits
    assert all(h["payload"]["document_id"] == "M06" for h in hits)


def test_semantic_rewrite_queries(retriever):
    """Addendum §31：语义改写必须命中正确章节。"""
    cases = [
        ("为什么先进光刻反而可能降低大芯片经济性？", ["High-NA", "拼接", "视场", "Stitching"]),
        ("为什么越先进的光刻机反而可能对超大 GPU 不划算", ["High-NA", "拼接", "429"]),
    ]
    corpus_texts = _chunk_texts()
    for q, keywords in cases:
        hits, _ = retriever.search(q, k=5)
        joined = " ".join(corpus_texts.get(h["payload"]["chunk_id"], "") for h in hits)
        assert any(kw in joined for kw in keywords), f"{q}: Top5 未命中 {keywords}"


def _chunk_texts() -> dict[str, str]:
    from app.lexical.corpus import build_corpus_db
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    conn, _ = build_corpus_db(tmp / "corpus.db")
    rows = conn.execute("SELECT id, plain_text FROM chunks").fetchall()
    conn.close()
    return {r["id"]: r["plain_text"] for r in rows}
