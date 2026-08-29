"""M2-03/04 heading tree 与行号测试。"""

from app.parser.markdown_parser import parse_markdown

DOC = """# 文档标题

引言块。

## 1.1 第一小节

内容 A。

### (1) 子要点甲

内容甲。

### (2) 子要点乙

内容乙。

## 1.2 第二小节

| 列1 | 列2 |
|---|---|
| a | b |

# 第 2 章 新章

章内容。
"""


def test_heading_tree_and_ids():
    doc = parse_markdown(DOC)
    ids = {s.heading: s.section_id for s in doc.sections}
    assert ids["1.1 第一小节"] == "ch1-1"
    assert ids["1.2 第二小节"] == "ch1-2"
    assert ids["(1) 子要点甲"] == "ch1-1:o1"
    assert ids["(2) 子要点乙"] == "ch1-1:o2"
    assert ids["第 2 章 新章"] == "ch2"

    # heading_path 自根至叶
    s = next(s for s in doc.sections if s.heading == "(1) 子要点甲")
    assert s.heading_path == ["文档标题", "1.1 第一小节", "(1) 子要点甲"]
    assert s.parent_id == "ch1-1"


def test_line_ranges_and_blocks():
    doc = parse_markdown(DOC)
    s = next(s for s in doc.sections if s.heading == "1.2 第二小节")
    # 标题在第 17 行，下一标题 "# 第 2 章" 在第 23 行 -> end_line = 22
    assert s.start_line == 17 and s.end_line == 22
    types = [b.block_type for b in s.blocks]
    assert "table" in types

    t = next(b for b in s.blocks if b.block_type == "table")
    assert t.start_line == 19 and t.end_line == 21
    assert t.text.startswith("| 列1 |")


def test_fences_mermaid_formula():
    doc = parse_markdown("""# 根

## 公式节

行内公式 $E=mc^2$ 的说明。

$$
F = G \\frac{m_1 m_2}{r^2}
$$

## 图节

```python
print("hello")
```

```mermaid
graph TD; A-->B;
```
""")
    formula_sec = next(s for s in doc.sections if s.heading == "公式节")
    assert any(b.block_type == "formula" for b in formula_sec.blocks)
    code_sec = next(s for s in doc.sections if s.heading == "图节")
    types = [b.block_type for b in code_sec.blocks]
    assert "code" in types and "mermaid" in types
