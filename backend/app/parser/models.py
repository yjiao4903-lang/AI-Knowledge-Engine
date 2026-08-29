"""Parser 数据模型（M2）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EVIDENCE_RE = re.compile(r"\[L([1-5])\]")


@dataclass
class Block:
    """节内块级对象（prose 段落 / 表格 / 代码 / mermaid / 公式 / ASCII 图）。"""

    block_type: str  # prose | table | code | mermaid | formula | ascii_diagram
    start_line: int  # 1-based，含
    end_line: int  # 1-based，含
    text: str
    lang: str | None = None  # code fence 语言


@dataclass
class Section:
    level: int  # 1..4
    heading: str
    heading_path: list[str]  # 自根至当前（含）
    section_id: str  # 不含 report_code 前缀，如 "ch3-2"、"ch1-1:o1"
    parent_id: str | None
    ordinal: int  # 文档内全局序号（0 = 文档根）
    start_line: int  # 标题行（1-based，含）
    end_line: int  # 1-based，含
    blocks: list[Block] = field(default_factory=list)
    section_type: str = "body"

    @property
    def raw_text(self) -> str:
        return "\n".join(self._lines) if self._lines else ""

    _lines: list[str] = field(default_factory=list, repr=False)

    def evidence_levels(self) -> list[int]:
        return sorted({int(m) for m in EVIDENCE_RE.findall(self.raw_text)})

    @property
    def evidence_level(self) -> int | None:
        levels = self.evidence_levels()
        return min(levels) if levels else None


@dataclass
class ParsedDocument:
    title: str
    metadata: dict  # 规范化键 + metadata_raw
    metadata_raw: dict  # 原样键值
    sections: list[Section]  # 含文档根 section（level 1 标题）
    warnings: list[str] = field(default_factory=list)
