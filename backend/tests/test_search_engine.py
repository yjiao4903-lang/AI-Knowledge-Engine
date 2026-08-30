"""M6 集成测试：Hybrid 引擎、RRF 融合、去重、Parent Boost、Debug Trace（Addendum §33-41）。

P0-1 解耦：使用 tests/fixtures 独立语料（conftest fixture_retrieval），
Qdrant collection + SQLite 均独立，断言基于 fixture 内容可复现，不依赖
dev/prod 的生产 corpus 与具体文档排名。
"""

import pytest


@pytest.fixture(scope="module")
def engine(fixture_retrieval):
    if fixture_retrieval is None:
        pytest.skip("fixture 语料不可用")
    return fixture_retrieval["engine"]


def test_hybrid_results_shape_and_timing(engine):
    resp = engine.search("HBM4 的接口位宽是多少？", top_k=5)
    assert resp["mode"] == "hybrid"
    assert len(resp["results"]) == 5
    r0 = resp["results"][0]
    assert {"rank", "chunk_id", "document_id", "heading_path", "content_type",
            "evidence_level", "snippet", "start_line", "end_line", "scores"} <= set(r0)
    assert {"dense_rank", "terms_rank", "trigram_rank", "rrf", "section_boost", "final"} <= set(r0["scores"])
    for k in ("embed_ms", "dense_ms", "terms_ms", "trigram_ms", "fusion_ms",
              "section_ms", "filter_ms", "total_ms"):
        assert k in resp["timing_ms"]
    assert resp["timing_ms"]["total_ms"] >= resp["timing_ms"]["fusion_ms"]


def test_no_duplicate_chunk_ids(engine):
    resp = engine.search("先进封装与 HBM4 的关系", top_k=10)
    ids = [r["chunk_id"] for r in resp["results"]]
    assert len(ids) == len(set(ids))


def test_rank_trace_records_ranks(engine):
    resp = engine.search("CoWoS-L 与 CoWoS-S 的区别", top_k=10)
    # 三路候选在融合中至少一路有 rank
    for r in resp["results"]:
        assert any(v is not None for v in r["scores"].values() if isinstance(v, int))


def test_search_modes(engine):
    dense_resp = engine.search("液冷 为什么 必然", mode="dense", top_k=5)
    lexical_resp = engine.search("液冷 为什么 必然", mode="lexical", top_k=5)
    hybrid_resp = engine.search("液冷 为什么 必然", mode="hybrid", top_k=5)
    assert dense_resp["mode"] == "dense" and lexical_resp["mode"] == "lexical"
    assert dense_resp["results"] and lexical_resp["results"] and hybrid_resp["results"]
    # dense 模式不走 FTS
    assert dense_resp["timing_ms"]["terms_ms"] == 0.0


def test_filter_through_hybrid(engine):
    resp = engine.search("数据中心", filters={"document_ids": ["M06"]}, top_k=10)
    assert resp["results"]
    assert all(r["document_id"] == "M06" for r in resp["results"])


def test_parent_boost_applied(engine):
    resp = engine.search("HBM4 接口位宽", top_k=10)
    boosts = {r["scores"]["section_boost"] for r in resp["results"]}
    assert 1.08 in boosts  # 命中 section prior 的候选被加成


def test_debug_trace(engine):
    resp = engine.search("混合键合 为什么 重要", debug=True, top_k=5)
    dbg = resp["debug"]
    assert "dense" in dbg["sources"] and "terms" in dbg["sources"] and "trigram" in dbg["sources"]
    assert dbg["boosted_sections"]
    assert dbg["fused_top"] and "rrf" in dbg["fused_top"][0]


def test_weighted_rrf_math():
    from app.retrieval.fusion import weighted_rrf

    fused = weighted_rrf(
        {"a": ["x", "y"], "b": ["y", "z"]},
        rrf_k=60, weights={"a": 1.0, "b": 1.0},
    )
    scores = {cid: s for cid, s, _ in fused}
    # y: a列rank2 + b列rank1 = 1/62+1/61 > x(1/61) > z(1/62？z=b列rank2=1/62)
    # y(0.0325) > x(0.0164) > z(0.0161)
    assert scores["y"] > scores["x"] > scores["z"]
    ranks = dict(fused[0][2])
    assert ranks == {"a": 2, "b": 1}
