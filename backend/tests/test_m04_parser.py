"""M2 验收：使用真实 M04 报告 fixture（spec §56）。

必须正确识别：报告 metadata、执行摘要、Chapter 1~6、Subsections、
监测看板、References、Audit。
"""

from pathlib import Path

from app.parser.markdown_parser import parse_markdown

M04_PATH = Path(__file__).parent / "fixtures" / "M04_sample.md"


def parse_m04():
    return parse_markdown(M04_PATH.read_text(encoding="utf-8"))


def test_m04_metadata():
    doc = parse_m04()
    md = doc.metadata
    assert md.get("report_code") == "M04"
    assert md.get("domain", "").startswith("Domain II")
    assert md.get("completed_at") == "2026-08-27"
    assert md.get("research_method", "").startswith("Flagship")


def test_m04_headings_ch1_to_ch6():
    doc = parse_m04()
    chs = {s.section_id: s for s in doc.sections if s.section_id.startswith("ch")}
    for i in range(1, 7):
        assert f"ch{i}" in chs, f"缺少第 {i} 章"
    # 编号 subsection
    assert "ch1-1" in chs and "ch3-2" in chs and "ch6-3" in chs
    # heading path
    s = chs["ch3-2"]
    assert s.heading_path[0].startswith("【旗舰战略研究报告】")
    assert "第 3 章" in s.heading_path[-2] if len(s.heading_path) > 1 else True
    assert s.heading_path[-1].startswith("3.2")


def test_m04_special_sections():
    doc = parse_m04()
    by_type = {}
    for s in doc.sections:
        by_type.setdefault(s.section_type, []).append(s)

    assert any("执行摘要" in s.heading for s in by_type.get("summary", []))
    assert any("参考文献" in s.heading for s in by_type.get("reference", []))
    assert any(s.section_type == "audit" for s in doc.sections)
    assert any("监测信号看板" in s.heading for s in by_type.get("monitoring", []))


def test_m04_blocks_preserved():
    doc = parse_m04()
    all_blocks = [b for s in doc.sections for b in s.blocks]
    types = {b.block_type for b in all_blocks}
    assert "table" in types
    assert "ascii_diagram" in types or "code" in types  # 顶部因果拓扑 ASCII 图
    # 表格行号连续且在文档范围内
    for b in all_blocks:
        assert 1 <= b.start_line <= b.end_line <= 816


def test_m04_evidence_levels():
    doc = parse_m04()
    # 根节段（标题+元数据+拓扑图）可无 [L] 标记
    # 执行摘要的子节包含 [L1] 标记（spec §13 证据等级）
    summary_children = [s for s in doc.sections if s.parent_id and
                        next(x for x in doc.sections if x.section_id == s.parent_id).heading.startswith("执行摘要")]
    assert summary_children, "执行摘要应有子节"
    assert any(s.evidence_level == 1 for s in summary_children)


def test_m04_no_duplicate_section_ids():
    doc = parse_m04()
    ids = [s.section_id for s in doc.sections]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert dupes == set(), f"重复 section_id: {dupes}"
