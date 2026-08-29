"""证据等级解析（M2-09，spec §13）。"""

from __future__ import annotations

import re

EVIDENCE_RE = re.compile(r"\[L([1-5])\]")


def extract_evidence_levels(text: str) -> list[int]:
    """出现顺序去重后的全部等级（供 evidence_levels_json 保留完整数组）。"""
    seen: list[int] = []
    for m in EVIDENCE_RE.finditer(text):
        lvl = int(m.group(1))
        if lvl not in seen:
            seen.append(lvl)
    return seen


def evidence_level_min(text: str) -> int | None:
    levels = extract_evidence_levels(text)
    return min(levels) if levels else None
