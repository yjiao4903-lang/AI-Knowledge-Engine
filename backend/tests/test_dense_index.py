"""M5 集成测试：Qdrant Dense 索引/检索/Metadata Filter（spec §25-32）。

P0-1 解耦：使用 tests/fixtures 独立语料（conftest fixture_retrieval），
Qdrant collection + SQLite 均独立，断言基于 fixture 内容可复现，不依赖
dev/prod 的生产 corpus 与具体文档排名。
"""

import pytest


@pytest.fixture(scope="module")
def retriever(fixture_retrieval):
    if fixture_retrieval is None:
        pytest.skip("fixture 语料不可用")
    return fixture_retrieval["dense"]


def test_search_returns_payload_and_scores(retriever):
    hits, embed_ms = retriever.search("HBM4 的接口位宽是多少？", k=5)
    assert len(hits) == 5
    for h in hits:
        p = h["payload"]
        assert {"chunk_id", "document_id", "section_id", "content_type", "evidence_level", "domain"} <= set(p)
        assert h["score"] > 0
    assert embed_ms >= 0


def test_exact_query_top(retriever):
    # fixture 确定性：EXE:5000 为 High-NA EUV 专有名词，仅出现在 M04 语料（fixtures/M04_sample.md）
    hits, _ = retriever.search("EXE:5000 的成本和吞吐问题", k=3)
    assert hits
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
