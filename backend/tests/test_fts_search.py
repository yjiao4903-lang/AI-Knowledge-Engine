"""M4 集成测试：FTS 索引一致性、检索模式、5 篇语料 Hit@5（Addendum §16-18/20）。"""

import pytest

from app.lexical.corpus import DEFAULT_FIXTURES, build_corpus_db
from app.lexical.fts_search import LexicalSearcher

EXACT_TERMS = [
    "CoWoS-L", "CoWoS-S", "High-NA", "EXE:5000", "HBM4", "HBM4E", "MR-MUF",
    "TC-NCF", "N3E", "N3B", "A16", "CFET", "BSPDN", "60mV/dec", "429mm²",
]
CHINESE_QUERIES = [
    "先进封装", "铜互连", "散热良率", "混合键合", "先进制程",
    "资本开支", "推理算力", "电网瓶颈", "半导体周期", "蛋白质结构",
]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    db = tmp_path_factory.mktemp("m4") / "corpus.db"
    conn, info = build_corpus_db(db)
    return conn, info


def test_fts_count_consistency(corpus):
    """chunks == fts_terms == fts_trigram（Addendum §16/75）。"""
    conn, info = corpus
    n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    n_terms = conn.execute("SELECT count(*) FROM chunks_fts_terms").fetchone()[0]
    n_trigram = conn.execute("SELECT count(*) FROM chunks_fts_trigram").fetchone()[0]
    assert n_chunks == n_terms == n_trigram > 700
    assert set(info["documents"].keys()) == {"M04", "M05", "M06", "M07", "M09", "M10", "M14", "M16", "M18", "M22"}


def test_exact_identifier_hit_at_5(corpus):
    """15 个技术 Identifier 查询 Hit@5（ground truth = plain_text 包含该词）。"""
    conn, _ = corpus
    searcher = LexicalSearcher(conn)
    passed, checked = 0, 0
    for term in EXACT_TERMS:
        truth = {
            r["chunk_id"]
            for r in conn.execute(
                "SELECT id AS chunk_id FROM chunks WHERE instr(plain_text, ?) > 0", (term,)
            ).fetchall()
        }
        if not truth:
            continue  # 语料中不存在的词跳过
        checked += 1
        hits = [h.chunk_id for h in searcher.search_terms(term, k=5)]
        assert hits, f"{term}: 无结果"
        if set(hits[:5]) & truth:
            passed += 1
        else:
            # trigram 应兜底命中
            tri = [h.chunk_id for h in searcher.search_trigram(term, k=5)]
            if set(tri[:5]) & truth:
                passed += 1
    assert checked >= 12, f"语料覆盖不足: {checked}"
    assert passed / checked >= 0.95, f"Exact Hit@5 = {passed}/{checked}"


def test_chinese_query_hit_at_5(corpus):
    """中文查询 Top5 至少出现正确章节（ground truth = 包含完整词组）。"""
    conn, _ = corpus
    searcher = LexicalSearcher(conn)
    passed, checked = 0, 0
    for q in CHINESE_QUERIES:
        truth = {
            r["chunk_id"]
            for r in conn.execute(
                "SELECT id AS chunk_id FROM chunks WHERE instr(plain_text, ?) > 0", (q,)
            ).fetchall()
        }
        if not truth:
            continue
        checked += 1
        fused, _ = searcher.search_combined(q)
        top5 = [cid for cid, _, _ in fused[:5]]
        assert top5, f"{q}: 无结果"
        if set(top5) & truth:
            passed += 1
    assert checked >= 6, f"语料覆盖不足: {checked}"
    assert passed / checked >= 0.7, f"Chinese Hit@5 = {passed}/{checked}"


def test_combined_records_ranks(corpus):
    conn, _ = corpus
    searcher = LexicalSearcher(conn)
    fused, timing = searcher.search_combined("HBM4 与 CoWoS-L 的关系")
    assert fused
    for _, _, ranks in fused[:3]:
        assert "terms" in ranks and "trigram" in ranks
    assert set(timing) == {"terms_ms", "trigram_ms", "fusion_ms"}


def test_multi_document_coverage(corpus):
    """中文查询结果应能跨文档（不只 M04）。"""
    conn, _ = corpus
    searcher = LexicalSearcher(conn)
    fused, _ = searcher.search_combined("资本开支", terms_k=20)
    docs = {cid.split(":")[0] for cid, _, _ in fused[:10]}
    assert len(docs) >= 2, f"Top10 只来自 {docs}"


def test_all_fixtures_present():
    for f in DEFAULT_FIXTURES:
        assert f.endswith("_sample.md")
