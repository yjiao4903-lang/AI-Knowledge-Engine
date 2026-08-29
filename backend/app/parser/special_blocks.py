"""块级对象识别（M2-05/06/07/08）：code fence、mermaid、表格、公式块、ASCII 图。"""

from __future__ import annotations

import re

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
FORMULA_BLOCK_RE = re.compile(r"^\s*\$\$\s*$")
MERMAID_HINT_RE = re.compile(r"(graph|flowchart|sequenceDiagram|erDiagram|gantt|stateDiagram)", re.I)
ASCII_ART_HINT_RE = re.compile(r"[─│┌┐└┘├┤┬┴┼═║╔╗╚╝▲▼──►◀]", re.I)


def detect_blocks(lines: list[str], start: int, end: int) -> list:
    """将 [start, end) 行区间切分为 Block 列表（M2-04 行号保留）。"""
    from app.parser.models import Block

    blocks: list[Block] = []
    i = start
    para_start: int | None = None

    def flush_para(upto: int) -> None:
        nonlocal para_start
        if para_start is not None and upto > para_start:
            text = "\n".join(lines[para_start:upto]).strip()
            if text:
                blocks.append(Block("prose", para_start + 1, upto, text))
        para_start = None

    while i < end:
        line = lines[i]

        m = FENCE_RE.match(line)
        if m:  # code / mermaid fence
            fence, lang = m.group(1), m.group(2) or None
            flush_para(i)
            j = i + 1
            while j < end and not re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", lines[j]):
                j += 1
            body = "\n".join(lines[i + 1 : j])
            block_type = "code"
            if (lang or "").lower() == "mermaid" or (lang is None and MERMAID_HINT_RE.search(body)):
                block_type = "mermaid"
            elif lang is None and ASCII_ART_HINT_RE.search(body):
                block_type = "ascii_diagram"
            blocks.append(Block(block_type, i + 1, j + 1, body, lang=lang))
            i = j + 1
            continue

        if TABLE_ROW_RE.match(line):  # 表格（连续 | 行）
            flush_para(i)
            j = i
            while j < end and TABLE_ROW_RE.match(lines[j]):
                j += 1
            blocks.append(Block("table", i + 1, j, "\n".join(lines[i:j])))
            i = j
            continue

        if FORMULA_BLOCK_RE.match(line):  # $$ ... $$ 公式块
            flush_para(i)
            j = i + 1
            while j < end and not FORMULA_BLOCK_RE.match(lines[j]):
                j += 1
            blocks.append(Block("formula", i + 1, min(j + 1, end), "\n".join(lines[i + 1 : j])))
            i = j + 1
            continue

        if line.strip():  # prose（空行分段）
            if para_start is None:
                para_start = i
        else:
            flush_para(i)
        i += 1

    flush_para(end)
    return blocks
