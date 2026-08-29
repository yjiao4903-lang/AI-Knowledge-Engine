"""M2-01/02/09 metadata 与证据等级测试。"""

from app.parser.evidence import evidence_level_min, extract_evidence_levels
from app.parser.markdown_parser import parse_markdown
from app.parser.metadata_parser import extract_report_code

BQ_DOC = """# 【旗舰战略研究报告】示例

> **专题代号**：`M04_Semiconductor_Physics_Limits_and_Packaging`  
> **所属领域**：Domain II · 计算物理底座  
> **研究方法**：Flagship Deep Research V3.0  
> **证据等级规范**：`[L1 因果证实 / L2 统计相关]`  
> **完成日期**：2026-08-27 ｜ **正文字数**：约 28,000 字  
> **首席技术官**：Antigravity Team  

## 1. 测试

正文 `[L2]` 与 `[L1]`。
"""

YAML_DOC = """---
report_id: M05
title: 测试报告
domain: Domain III
completed_at: 2026-08-28
status: final
---

# 标题

正文
"""


def test_blockquote_metadata():
    doc = parse_markdown(BQ_DOC)
    md = doc.metadata
    assert md["report_code"] == "M04"  # 提取前缀代号
    assert md["domain"].startswith("Domain II")
    assert md["completed_at"] == "2026-08-27"
    assert md["author"] == "Antigravity Team"
    assert md["word_count"].startswith("约 28,000")
    assert md["title"] == "【旗舰战略研究报告】示例"


def test_yaml_front_matter():
    doc = parse_markdown(YAML_DOC)
    md = doc.metadata
    assert md["report_id"] == "M05"
    assert md["completed_at"] == "2026-08-28"
    assert md["status"] == "final"


def test_extract_report_code():
    assert extract_report_code("M04_Semiconductor_Physics") == "M04"
    assert extract_report_code("M12_x") == "M12"
    assert extract_report_code("XYZ99_ab") == "XYZ99"
    assert extract_report_code(None) is None


def test_evidence_levels():
    text = "结论 A [L1]。结论 B [L3]。补充 [L1] 重复。"
    assert extract_evidence_levels(text) == [1, 3]
    assert evidence_level_min(text) == 1
    assert extract_evidence_levels("无标记文本") == []
    assert evidence_level_min("无标记文本") is None
