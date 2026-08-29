"""Heading Tree（M2-03）与 Section ID 生成。"""

from __future__ import annotations

import re

CH_RE = re.compile(r"^第\s*([0-9一二三四五六七八九十]+)\s*章")
NUM_RE = re.compile(r"^(\d+(?:\.\d+)+)")
SINGLE_NUM_RE = re.compile(r"^(\d+)$")
PAREN_RE = re.compile(r"^[（(](\d+)[）)]")


def section_id_for(level: int, heading: str, parent_id: str | None, global_ordinal: int) -> str:
    """根据标题编号生成 section_id（global_ordinal 为文档内全局序号，0=文档根）。

    - "第 3 章 ..."  -> "ch3"
    - "3.2 ..."      -> parent_id="ch3" 时 "ch3-2"
    - "(2) ..."      -> f"{parent_id}:o2"
    - 无编号         -> 有父节点 f"{parent_id}:o{global_ordinal}"，顶层 f"top{global_ordinal}"
    """
    m = CH_RE.match(heading)
    if m:
        return f"ch{_cn_to_int(m.group(1))}"
    m = NUM_RE.match(heading)
    if m:
        parts = m.group(1).split(".")
        if parent_id and parent_id.startswith("ch") and parts[0] == parent_id[2:]:
            return f"{parent_id}-{parts[1]}" if len(parts) == 2 else f"{parent_id}-{'-'.join(parts[1:])}"
        return "ch" + "-".join(parts)
    m = SINGLE_NUM_RE.match(heading)
    if m and parent_id in (None, ""):
        return f"ch{m.group(1)}"
    m = PAREN_RE.match(heading)
    if m and parent_id:
        return f"{parent_id}:o{m.group(1)}"
    if parent_id:
        return f"{parent_id}:o{global_ordinal}"
    return f"top{global_ordinal}"


_CN_NUMS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(s: str) -> int:
    """中文数字转 int；支持复合形式（十一=11、二十三=23、一百零四…）。

    I0 全量语料修复：此前仅支持单字（一..十），"第十一章" 被判为 0 导致
    多个 section 撞名 ch0（sections UNIQUE 约束失败，无法索引）。
    """
    if s.isdigit():
        return int(s)
    units = {"十": 10, "百": 100}
    total, num = 0, 0
    for ch in s.strip():
        if ch in units:  # 十/百 须先于 _CN_NUMS 判断（"十" 亦在 _CN_NUMS）
            total += (num or 1) * units[ch]
            num = 0
        elif ch in _CN_NUMS:
            num = _CN_NUMS[ch]
        elif ch == "零":
            continue
        else:
            return 0
    return total + num


# --- M2-10 Section 类型分类 ---
SECTION_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("summary", ("执行摘要", "executive summary")),
    ("toc", ("目录", "table of contents")),
    ("reference", ("参考文献", "references", "资料来源")),
    ("audit", ("审计", "验收核查")),
    ("monitoring", ("监测信号看板", "监测指标", "监测看板")),
    ("decision_tree", ("决策树",)),
    ("comparison", ("对比", "差异", "vs")),
    ("causal_chain", ("因果",)),
]


def classify_section_type(heading: str) -> str:
    h = heading.lower()
    for stype, keywords in SECTION_TYPE_RULES:
        if any(k.lower() in h for k in keywords):
            return stype
    return "body"
