"""M3 单元测试：分块规则、特殊块保全、三文本、ID 稳定、行号、证据继承。"""

from app.chunking.chunk_models import CHUNKER_VERSION, build_chunk_id
from app.chunking.plain_text import to_plain_text
from app.chunking.qa import compute_stats, validate_chunks
from app.chunking.semantic_chunker import SemanticChunker
from app.core.config import ChunkingConfig
from app.parser.markdown_parser import parse_markdown

CFG = ChunkingConfig()


def chunk(doc_text: str, document_id: str = "M01") -> list:
    return SemanticChunker(CFG).chunk_document(parse_markdown(doc_text), document_id)


def test_chunk_id_stable():
    assert build_chunk_id("M04", "ch3-2", 4) == "M04:ch3-2:0004"
    doc = """# 标题

## 1.1 节

段落甲。

段落乙。
"""
    c1 = chunk(doc)
    c2 = chunk(doc)
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]  # 确定性，无 UUID


def test_table_kept_whole():
    doc = """# 标题

## 1.1 节

引导段落。

| 型号 | 位宽 |
|---|---|
| HBM4 | 2048-bit |
| HBM3E | 1024-bit |

收尾段落。
"""
    chunks = chunk(doc)
    table_chunks = [c for c in chunks if c.content_type == "table"]
    assert len(table_chunks) == 1
    assert "HBM4 | 2048-bit" in table_chunks[0].plain_text or "HBM4" in table_chunks[0].plain_text
    # 表格 chunk 不包含前后 prose
    assert "引导段落" not in table_chunks[0].raw_markdown
    assert "收尾段落" not in table_chunks[0].raw_markdown


def test_oversized_table_single_chunk():
    rows = "\n".join(f"| 项目{i} | 数值{i} {"x" * 80} |" for i in range(40))
    doc = f"""# 标题

## 1.1 节

| 列A | 列B |
|---|---|
{rows}
"""
    chunks = chunk(doc)
    tables = [c for c in chunks if c.content_type == "table"]
    assert len(tables) == 1  # 不允许断表
    assert tables[0].oversized is True


def test_formula_attaches_explanation():
    doc = """# 标题

## 1.1 节

上述公式的物理含义是电阻率随截面缩小而激增。

$$
\\rho(n) = \\rho_0 + \\frac{A}{n}
$$

后续独立段落内容，与公式无直接相邻关系，长度较长以便区分。它讲述铜互连在亚 20nm 节点的表面散射与晶界散射问题，并给出实际产线数据与良率影响分析，确保不被并入公式块。
"""
    chunks = chunk(doc)
    formula = [c for c in chunks if c.content_type == "formula"]
    assert len(formula) == 1
    assert "电阻率随截面缩小" in formula[0].raw_markdown  # 紧邻解释已附带
    assert "$$" in formula[0].raw_markdown
    # 后续长段不被并入
    assert "良率影响分析" not in formula[0].raw_markdown
    assert any("良率影响分析" in c.plain_text for c in chunks)


def test_prose_split_respects_limits():
    paras = "\n\n".join(f"段落{i}：" + "内容" * 150 for i in range(8))  # 每段 ~330 字
    doc = f"# 标题\n\n## 1.1 节\n\n{paras}\n"
    chunks = chunk(doc)
    prose = [c for c in chunks if c.content_type == "prose"]
    assert len(prose) >= 2
    for c in prose:
        assert len(c.plain_text) <= CFG.hard_max_chars
    # 行号连续不跨节
    for c in prose:
        assert c.start_line <= c.end_line


def test_embedding_text_context():
    doc = """# 标题甲

## 1.1 玻尔兹曼极限

[L1] 正文内容。
"""
    chunks = chunk(doc, "M04")
    c = chunks[0]
    assert c.embedding_text.startswith("Document: 标题甲")
    assert "Section:" in c.embedding_text and "1.1 玻尔兹曼极限" in c.embedding_text
    assert "Evidence: L1" in c.embedding_text
    assert c.embedding_text.endswith("[L1] 正文内容。") or "正文内容" in c.embedding_text


def test_plain_text_keeps_tech_terms():
    md = "**HBM4** 使用 `CoWoS-L` 封装，阈值 `60mV/dec`，见 [文档](http://x.y)。"
    plain = to_plain_text(md)
    assert "HBM4" in plain and "CoWoS-L" in plain and "60mV/dec" in plain
    assert "http://x.y" not in plain and "文档" in plain
    assert "**" not in plain and "`" not in plain


def test_evidence_inheritance():
    doc = """# 标题

## 1.1 节

无标记段落，但 Section 内其他 chunk 有 [L2] 标记。

[L2] 有标记段落。
"""
    chunks = chunk(doc)
    unmarked = next(c for c in chunks if "无标记段落" in c.plain_text)
    assert unmarked.evidence_level == 2  # 继承 Section 等级
    assert 2 in unmarked.evidence_levels


def test_no_cross_section_chunks():
    doc = """# 标题

## 1.1 节甲

甲的内容。

## 1.2 节乙

乙的内容。
"""
    chunks = chunk(doc)
    v = validate_chunks(chunks, parse_markdown(doc), doc_line_count=len(doc.splitlines()))
    assert v["cross_section"] == 0
    for c in chunks:
        assert c.section_id in ("top1", "ch1-1", "ch1-2")


def test_validate_gate_clean_doc():
    doc = """# 标题

## 1.1 节

| a | b |
|---|---|
| 1 | 2 |

正文段落 [L1]。
"""
    chunks = chunk(doc)
    v = validate_chunks(chunks, parse_markdown(doc), doc_line_count=len(doc.splitlines()))
    assert v["gate_passed"], v


def test_chunker_version_constant():
    assert CHUNKER_VERSION
    stats = compute_stats(chunk("# 标题\n\n## 1.1 节\n\n内容。\n"))
    assert stats["chunk_count"] >= 1
