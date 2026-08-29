"""plain_text 清洗（M3-07）。

适度去除 Markdown 标记，但保留技术词、数字、公式文本与单位：
HBM4 / CoWoS-L / EXE:5000 / 60mV/dec 等不得被清洗掉。
"""

from __future__ import annotations

import re

# 链接 [text](url) -> text；图片整行删除
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
EMPH_RE = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|__(.+?)__|_(.+?)_")
CODE_RE = re.compile(r"`([^`]+)`")
HEADING_RE = re.compile(r"^#{1,6}\s+", re.M)


def to_plain_text(markdown: str) -> str:
    text = IMAGE_RE.sub("", markdown)
    text = LINK_RE.sub(r"\1", text)
    text = CODE_RE.sub(r"\1", text)
    # 表格行：| a | b | -> a | b（保留竖线分隔，技术词完整）
    text = re.sub(r"^\s*\|", "", text, flags=re.M)
    text = re.sub(r"\|\s*$", "", text, flags=re.M)
    # 表格分隔行 |---|---| 删除
    text = re.sub(r"^\s*\|?[\s:|-]+\|?\s*$", "", text, flags=re.M)
    text = HEADING_RE.sub("", text)
    text = EMPH_RE.sub(lambda m: next(g for g in m.groups() if g is not None), text)
    # 清理多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
