"""Metadata 解析（M2-01 YAML Front Matter / M2-02 旧式 Blockquote）。

支持两种格式（spec §10.2）：
A. YAML front matter（--- 围栏）
B. 旧式 blockquote：> **专题代号**：`M04_xxx` ｜ **完成日期**：2026-08-27
"""

from __future__ import annotations

import re

BOLD_KEY_RE = re.compile(r"\*\*(.+?)\*\*[：:]\s*")

# 旧式键 -> 规范化键
KEY_MAP = {
    "专题代号": "report_code",
    "报告代号": "report_code",
    "所属领域": "domain",
    "研究方法": "research_method",
    "证据等级规范": "evidence_spec",
    "完成日期": "completed_at",
    "正文字数": "word_count",
    "首席技术官": "author",
    "作者": "author",
    "标题": "title",
    "状态": "status",
    "报告编号": "report_code",
    "报告 ID": "report_id",
    "report_id": "report_id",
    "domain": "domain",
    "completed_at": "completed_at",
    "status": "status",
    "title": "title",
}

REPORT_CODE_RE = re.compile(r"^[A-Za-z]{1,6}\d+")


def extract_report_code(report_code: str | None) -> str | None:
    """'M04_Semiconductor_Physics' -> 'M04'；无法提取时返回 None。"""
    if not report_code:
        return None
    m = REPORT_CODE_RE.match(report_code.strip())
    return m.group(0) if m else report_code.strip()


def parse_front_matter(lines: list[str]) -> tuple[dict, int]:
    """解析 YAML front matter。返回 (metadata, 消耗行数)（无则 ({}，0)）。"""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, 0
    import yaml

    try:
        data = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return {}, end + 1
    if not isinstance(data, dict):
        return {}, end + 1
    return _normalize(data), end + 1


def parse_blockquote_metadata(lines: list[str], start: int = 0) -> tuple[dict, int]:
    """解析文档开头（或指定位置）的 blockquote 元数据行。

    返回 (metadata, 消耗的行数)。跳过起始空行；遇到非 `>` 非空行即停止。
    """
    metadata: dict = {}
    consumed = 0
    i = start
    while i < len(lines) and not lines[i].strip():
        i += 1  # 跳过起始空行（H1 与 blockquote 之间常有空行）
    while i < len(lines):
        line = lines[i]
        if not line.lstrip().startswith(">"):
            break
        content = line.lstrip().lstrip(">").strip()
        if not content:
            i += 1
            continue
        _parse_kv_line(content, metadata)
        consumed = i - start + 1
        i += 1
    return _normalize(metadata), consumed


def _parse_kv_line(content: str, metadata: dict) -> None:
    """一行可含多个键值对（以 ｜ 或 | 分隔）。键为 **粗体**。"""
    # 按全角/半角竖线切分，但避免切掉 ** 内部（键不含竖线，安全）
    for part in re.split(r"\s*[｜|]\s*", content):
        m = BOLD_KEY_RE.search(part)
        if not m:
            continue
        key = m.group(1).strip()
        value = part[m.end() :].strip().rstrip("*").strip()
        value = value.strip("`").strip()
        metadata[key] = value


def _normalize(raw: dict) -> dict:
    out: dict = {}
    for k, v in raw.items():
        canon = KEY_MAP.get(k.strip(), None)
        if canon:
            out[canon] = str(v).strip() if v is not None else ""
        else:
            out[k.strip()] = v
    if "report_code" in out:
        code = extract_report_code(out["report_code"])
        if code:
            out["report_code"] = code
    return out
