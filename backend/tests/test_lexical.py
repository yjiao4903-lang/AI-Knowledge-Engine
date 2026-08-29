"""M4 单元测试：Identifier 保护、lexical_text、Safe Query Parser（Addendum §9/13）。"""

import pytest

from app.core.errors import SqliteError
from app.lexical.normalizer import extract_identifiers, is_identifier, normalize
from app.lexical.query_parser import (
    build_terms_expression,
    build_trigram_expression,
    parse_query,
)
from app.lexical.tokenizer import build_lexical_text


def test_identifier_protection():
    for tok in ("CoWoS-L", "EXE:5000", "High-NA", "60mV/dec", "429mm²", "HBM4E", "MR-MUF", "TC_NCF", "A16+"):
        assert is_identifier(tok), tok


def test_extract_identifiers_order_and_dedup():
    text = "台积电 CoWoS-L 与 CoWoS-S 差异；EXE:5000 单台 $4 亿；引脚 429mm²。"
    idents = extract_identifiers(text)
    assert idents[0] == "CoWoS-L"
    assert "CoWoS-S" in idents and "EXE:5000" in idents
    assert len([i for i in idents if i == "CoWoS-L"]) == 1  # 去重


def test_lexical_text_keeps_identifiers_whole():
    text = "SK 海力士 MR-MUF 对比三星 TC-NCF 的 2.5 倍导热系数，HBM4 转向 2048-bit。"
    lex = build_lexical_text(text)
    assert "MR-MUF" in lex
    assert "TC-NCF" in lex
    assert "HBM4" in lex
    assert "2048-bit" in lex
    # 不允许被拆碎
    assert "MUF" not in lex.replace("MR-MUF", "")
    assert lex.index("MR-MUF") < lex.index("海力士") or "海力士" in lex  # 标识符前置或保留


def test_chinese_terms_tokenized():
    lex = build_lexical_text("先进封装与混合键合成为第一生产力，散热良率决定生死。")
    for term in ("先进封装", "混合键合", "散热良率", "生产力"):
        assert term in lex, term


def test_nfkc_normalize():
    assert normalize("ＨＢＭ４  全角") == "HBM4 全角"  # 全角转半角


# ---- Query Parser ----

def test_terms_expression_quotes_identifiers():
    expr = build_terms_expression("CoWoS-L 与 HBM4 的关系")
    assert '"CoWoS-L"' in expr and '"HBM4"' in expr
    # 标识符不会被裸露（会被 FTS 解释为 column filter）
    for ident in ("CoWoS-L", "HBM4"):
        i = expr.index(ident)
        assert expr[i - 1] == '"' and expr[i + len(ident)] == '"'


def test_trigram_expression_minimum_length():
    expr = build_trigram_expression("CoWoS-L 与 HBM 的产能")
    assert '"CoWoS-L"' in expr
    assert '"HBM"' not in expr  # 3 字符 "HBM" 其实可以；确保无 <3 词项
    for part in expr.split(" OR "):
        inner = part.strip('"')
        assert len(inner) >= 3


def test_special_char_queries_no_syntax_error(tmp_path):
    """Addendum §13：特殊字符查询必须无 FTS 语法错误（含合成语料）。"""
    from app.lexical.corpus import build_corpus_db

    conn, _ = build_corpus_db(tmp_path / "spec.db", fixture_names=["M04_sample.md"])
    # 注入含特殊字符形态的合成 chunk（仅测试库，不动知识源）
    from app.storage.repositories.knowledge import ChunkRepository, DocumentRepository, SectionRepository

    with conn:
        DocumentRepository(conn).upsert({
            "id": "SYN", "title": "合成文档", "source_path": "D:/fixtures/SYN.md",
            "file_name": "SYN.md", "sha256": "syn",
        })
        SectionRepository(conn).replace_for_document([
            {"id": "SYN:ch1", "document_id": "SYN", "level": 2, "heading": "ch1",
             "heading_path": "SYN > ch1", "ordinal": 1}
        ])
        ChunkRepository(conn).upsert_batch([
            {
                "id": "SYN:ch1:0001", "document_id": "SYN", "section_id": "SYN:ch1",
                "ordinal": 1, "heading_path": "SYN > ch1", "content_type": "prose",
                "raw_markdown": "A16+ 提升幅度对比 N3.E 与 TC_NCF 组合。", "plain_text": "A16+ 提升幅度对比 N3.E 与 TC_NCF 组合。",
                "embedding_text": "A16+ N3.E TC_NCF", "lexical_text": build_lexical_text("A16+ 提升幅度对比 N3.E 与 TC_NCF 组合。"),
                "content_hash": "x1",
            }
        ])
    from app.lexical.fts_search import LexicalSearcher

    searcher = LexicalSearcher(conn)
    for q in ("High-NA", "EXE:5000", "60mV/dec", "A16+", "N3.E", "TC_NCF", "CoWoS-L 与 HBM4 的关系"):
        # 不抛 SqliteError 即通过
        searcher.search_terms(q, k=5)
        searcher.search_trigram(q, k=5)
    # 合成语料精确命中
    hits = searcher.search_terms("TC_NCF", k=5)
    assert any(h.chunk_id == "SYN:ch1:0001" for h in hits)
    conn.close()
