"""I0 全量语料收录与 doc_id 策略（ADR-013）。

背景：`D:\AI深度报告归档` 是研究流水线产物库（7159 个 .md，归档自身权威索引
V3.1 定义了成品层/工作层/历史层），同一主题的 00-12 阶段文件共享同一专题代号，
多层镜像目录内容重复。直接全量索引会导致 doc_id 静默覆盖与检索污染。

策略（全部排除均记录 Exclusion Reason + Count，禁止静默丢弃）：
  - EXCLUDED_DIR      ：工作层/历史层目录（研究输出、版本存档、03_历史版本存档、
                        根级冗余、_废弃_旧镜像、research-expert-team、.agents）
  - EXCLUDED_PROCESS  ：阶段文件（stem 匹配 ^0\\d[a-z]?_ 或 ^10_，或含"开题报告"）
  - EXCLUDED_DUPLICATE：(doc_id, sha256) 与 canonical 文件完全相同的拷贝
  - doc_id 规则（按序取第一个命中）：
      1) stem 含"思维增量"      -> <base>__思维增量
      2) stem 含"负知识"        -> <base>__负知识
      3) metadata report_code   -> 该值（extract_report_code 已归一为 M04 形态）
      3b) stem 匹配 ^(M\d{1,2})_ -> 提取代号（M14/M19 等缺专题代号的旗舰文件）
      4) stem == "11_最终报告"  -> 父主题目录名
      5) 其余                   -> stem
    base = report_code（若有）否则父主题目录名
  - 同 doc_id 不同内容 -> canonical 保留原 id，其余追加 "__" + sha256[:8]
    （DISAMBIGUATED 计数）。canonical 排序：最终报告 > 其他种类 > 目录优先级
    （02 成品层优先）> 路径长度 > 字典序
  - 该消歧同时覆盖 catalog 既有文档（跨批次）：若新候选的 default_doc_id
    与库内文档相同但内容不同，库内文档保留裸 id，新候选一律追加 sha8，
    禁止 index_file 以 DELETE+替换方式静默覆盖既有文档。
  - 若某 sha 组为 catalog 既有内容的重复拷贝，则该组全部路径记为重复，
    不得留下未分配候选（避免 apply_scan 回退到默认 doc_id 再次写入）。

canonical 优先级：02_主题研究报告 > 01_综合主报告 > 旗舰战略专题报告_完整备份_M01-M24
> 其余；同优先级取较短路径，再取字典序（确定性）。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

EXCLUDED_DIRS = {
    "研究输出", "版本存档", "03_历史版本存档", "根级冗余",
    "_废弃_旧镜像", "research-expert-team", ".agents",
}
PROCESS_STEM_RE = re.compile(r"^(0\d[a-z]?|10)_")
DIR_PRIORITY = {
    "02_主题研究报告": 0,
    "01_综合主报告": 1,
    "旗舰战略专题报告_完整备份_M01-M24": 2,
}


@dataclass
class IndexPlan:
    assignments: dict[str, str] = field(default_factory=dict)   # path -> doc_id
    exclusions: list[dict] = field(default_factory=list)        # {path, reason, detail}
    disambiguated: int = 0
    excluded_paths: set[str] = field(default_factory=set)


def exclusion_reason(path: str) -> str | None:
    p = Path(path)
    if any(part in EXCLUDED_DIRS for part in p.parts[:-1]):
        return "EXCLUDED_DIR"
    if "开题报告" in p.stem or PROCESS_STEM_RE.match(p.stem):
        return "EXCLUDED_PROCESS"
    if "最终报告" not in p.stem:
        return "EXCLUDED_NON_FINAL"
    return None


def default_doc_id(path: str, report_code: str | None) -> str:
    p = Path(path)
    stem = p.stem
    base = report_code or p.parent.name
    if "思维增量" in stem:
        return f"{base}__思维增量"
    if "负知识" in stem:
        return f"{base}__负知识"
    if report_code:
        return report_code
    m = re.match(r"^(M\d{1,2})_", stem)
    if m:
        return m.group(1)
    if stem == "11_最终报告":
        return p.parent.name
    return stem


def _canonical_key(path: str) -> tuple:
    """canonical 排序：最终报告优先，再按目录优先级/路径长度/字典序。"""
    p = Path(path)
    top = next((part for part in p.parts if part in DIR_PRIORITY), "9")
    kind = 0 if "最终报告" in p.stem else 1
    return (kind, DIR_PRIORITY.get(top, 9), len(path), path)


def build_index_plan(scan_result, conn: sqlite3.Connection) -> IndexPlan:
    """按 ScanResult 生成收录/命名计划。

    items: NEW/MODIFIED 且未命中排除规则的文件（需 report_code + sha256）。
    existing: catalog 中已存在文档（rescan 幂等 / 与历史部分索引去重）。
    """
    plan = IndexPlan()
    candidates: list[tuple[str, str, str]] = []  # (path, default_id, sha)

    for st in scan_result.states:
        if st.status in ("NEW", "MODIFIED"):
            reason = exclusion_reason(st.path)
            if reason:
                plan.exclusions.append({"path": st.path, "reason": reason})
                plan.excluded_paths.add(st.path)
                continue
            candidates.append((st.path, st.document_id or "", st.sha256 or ""))

    if not candidates:
        return plan

    # report_code 解析（仅 included 候选）
    from app.parser.markdown_parser import parse_markdown

    parsed_ids: dict[str, str] = {}
    for path, _, _ in candidates:
        try:
            text = Path(path).read_text(encoding="utf-8")
            parsed_ids[path] = parse_markdown(text).metadata.get("report_code") or ""
        except (OSError, UnicodeDecodeError):
            parsed_ids[path] = ""  # 编码/读取错误留给 pipeline 抛 SourceFileError

    # catalog 已有文档（id -> (sha, source_path)）
    existing: dict[str, tuple[str, str]] = {
        r["id"]: (r["sha256"] or "", r["source_path"])
        for r in conn.execute(
            "SELECT id, sha256, source_path FROM documents").fetchall()
    }

    groups: dict[str, list[tuple[str, str]]] = {}  # default_id -> [(path, sha)]
    for path, _, sha in candidates:
        did = default_doc_id(path, parsed_ids.get(path) or None)
        groups.setdefault(did, []).append((path, sha))

    for did, members in groups.items():
        ex = existing.get(did)
        # 同 (id, sha) 拷贝去重：保留 canonical
        by_sha: dict[str, list[str]] = {}
        for path, sha in members:
            by_sha.setdefault(sha, []).append(path)
        kept: list[tuple[str, str]] = []  # (path, sha)
        for sha, paths in by_sha.items():
            paths.sort(key=_canonical_key)
            keep = paths[0]
            if ex and ex[0] == sha and ex[1] != keep:
                # catalog 已有同内容文档：本 sha 组全部是重复拷贝，需整组排除，
                # 否则未被标记的副本会在 apply_scan 中回退写入（manifest 路径抖动）。
                for dup in paths:
                    plan.exclusions.append({"path": dup, "reason": "EXCLUDED_DUPLICATE",
                                            "detail": f"已由 {ex[1]} 以相同内容索引 (sha256:{sha[:8]})"})
                    plan.excluded_paths.add(dup)
                continue
            kept.append((keep, sha))
            for dup in paths[1:]:
                plan.exclusions.append({"path": dup, "reason": "EXCLUDED_DUPLICATE",
                                        "detail": f"与 {keep} 内容相同 (sha256:{sha[:8]})"})
                plan.excluded_paths.add(dup)
        if not kept:
            continue
        kept.sort(key=lambda item: _canonical_key(item[0]))
        owner = ex[1] if ex else None
        if ex is None:
            # 同批内冲突：canonical（路径排序首个）保留裸 id
            for i, (path, sha) in enumerate(kept):
                if i == 0:
                    plan.assignments[path] = did
                else:
                    plan.assignments[path] = f"{did}__{sha[:8]}"
                    plan.disambiguated += 1
        else:
            # 跨批次冲突：裸 id 只归库内文档当前的 source_path（同文档更新），
            # 其余不同内容候选一律 sha8 消歧，保证既有文档不被覆盖。
            for path, sha in kept:
                if path == owner:
                    plan.assignments[path] = did
                else:
                    plan.assignments[path] = f"{did}__{sha[:8]}"
                    plan.disambiguated += 1
    return plan
