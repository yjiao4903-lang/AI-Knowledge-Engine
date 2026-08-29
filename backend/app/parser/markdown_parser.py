"""Markdown 结构 Parser 主入口（M2）。

流程：行扫描 -> metadata（front matter / blockquote）-> heading 切分 ->
heading tree / section id / section type -> 块级对象识别 -> 证据等级。

所有 Section/Block 保留 1-based 行号（start_line/end_line，含端点）。
"""

from __future__ import annotations

import re

from app.parser.heading_tree import classify_section_type, section_id_for
from app.parser.metadata_parser import parse_blockquote_metadata, parse_front_matter
from app.parser.models import ParsedDocument, Section
from app.parser.special_blocks import detect_blocks

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def parse_markdown(text: str) -> ParsedDocument:
    lines = text.splitlines()
    warnings: list[str] = []

    # 1) metadata：YAML front matter 在文档顶部；否则 blockquote 元数据
    #    通常紧跟在 H1 标题之后，因此在顶部与首个标题行之后各尝试一次。
    metadata, consumed = parse_front_matter(lines)
    if not metadata:
        metadata, _ = parse_blockquote_metadata(lines, 0)
    if not metadata:
        for idx, line in enumerate(lines):
            if line.startswith("# "):
                metadata, consumed_bq = parse_blockquote_metadata(lines, idx + 1)
                break

    # 2) heading 切分
    headings: list[tuple[int, int, str]] = []  # (line_idx, level, heading)
    for idx, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= 4:
            headings.append((idx, len(m.group(1)), m.group(2).strip()))

    if not headings:
        sections = [
            Section(
                level=1, heading="(untitled)", heading_path=["(untitled)"],
                section_id="top1", parent_id=None, ordinal=0,
                start_line=1, end_line=len(lines), section_type="body",
            )
        ]
        sections[0].blocks = detect_blocks(lines, 0, len(lines))
        sections[0]._lines = lines[:]
        return ParsedDocument(title="", metadata=metadata, metadata_raw={}, sections=sections, warnings=warnings)

    # 3) 构造 section（标题行至下一标题前一行）
    raw_sections: list[Section] = []
    ordinal = 0
    for h_idx, (line_idx, level, heading) in enumerate(headings):
        end_idx = headings[h_idx + 1][0] - 1 if h_idx + 1 < len(headings) else len(lines) - 1
        # 吸收标题后的连续 --- 分隔线与空行不额外处理（保留在区间内）

        # 父节点：此前最近的更浅 level
        parent: Section | None = None
        for s in reversed(raw_sections):
            if s.level < level:
                parent = s
                break

        ordinal += 1
        parent_id = parent.section_id if parent else None
        sid = section_id_for(level, heading, parent_id, ordinal)
        raw_sections.append(
            Section(
                level=level,
                heading=heading,
                heading_path=(parent.heading_path if parent else []) + [heading],
                section_id=sid,
                parent_id=parent_id,
                ordinal=ordinal - 1,
                start_line=line_idx + 1,
                end_line=max(end_idx + 1, line_idx + 1),
                section_type=classify_section_type(heading),
            )
        )

    # 4) 块级识别与 raw 文本
    for s in raw_sections:
        body_start_idx = s.start_line  # 标题行是第 s.start_line 行（1-based）
        s._lines = lines[s.start_line - 1 : s.end_line]
        s.blocks = detect_blocks(lines, body_start_idx, s.end_line)

    # 5) 文档级信息
    title = headings[0][2]
    # heading_path 以文档标题为根（spec §10.3）：M04 类文档的章从 H1 重新开始，
    # 标准树语义下其祖先链不含标题，故统一前置。
    if raw_sections and raw_sections[0].heading == title:
        for s in raw_sections[1:]:
            if s.heading_path[0] != title:  # 已链到根的不重复前置
                s.heading_path = [title] + s.heading_path

    # 校验 section id 唯一性（编号重复的文档会把 :o 序号兜底）
    seen: dict[str, int] = {}
    for s in raw_sections:
        seen[s.section_id] = seen.get(s.section_id, 0) + 1
    for sid, n in seen.items():
        if n > 1:
            warnings.append(f"duplicate section_id: {sid} x{n}")

    root = raw_sections[0]  # 文档 H1 根节点
    metadata.setdefault("title", title)
    return ParsedDocument(title=title, metadata=metadata, metadata_raw=metadata, sections=raw_sections, warnings=warnings)
