# -*- coding: utf-8 -*-
"""P8 退化章节统计（H5 / 规范 §11.2、§8.2；只读）。

按 domain 与派生 corpus_tier 统计：section 数、占位标题占比、平均/分位 chunk 长度、chunk 数分布。
输出 `p8_analysis/degenerate_sections.json`。
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

E = Path(r"E:\研报提取资料库")
CATALOG = r"D:/AI-Knowledge-Engine/data/catalog_full.db"
OUT = E / "p8_analysis" / "degenerate_sections.json"

PLACEHOLDER_PATTERNS = [
    ("meta", re.compile(r"^元信息$")),
    ("image_n", re.compile(r"^配图\d*$")),
    ("chart_ocr", re.compile(r"^图表（p\d+ OCR）$")),
    ("image_prefix", re.compile(r"^配图资料[:：]")),
    ("empty", re.compile(r"^\s*$")),
]

TIER_BY_DOMAIN = {
    "外资研报": "formal_report",
    "科技日报": "daily", "中港交易台": "daily", "北美交易台": "daily", "SemiAnalysis": "daily",
    "即时讨论": "discussion",
    "配图资料": "image_material",
    "公众号": "other", "宏观": "other",
}


def tier_of(domain, source_path):
    if (source_path or "").lower().startswith("d:\\ai"):
        return "flagship"
    return TIER_BY_DOMAIN.get(domain or "", "other")


def is_placeholder(heading: str):
    for name, pat in PLACEHOLDER_PATTERNS:
        if pat.match(heading or ""):
            return name
    return None


def pctl(vals, p):
    vals = sorted(vals)
    return vals[min(int(len(vals) * p), len(vals) - 1)] if vals else 0


def main() -> int:
    conn = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    docs = {r["id"]: r for r in conn.execute("SELECT id, domain, source_path FROM documents")}

    sec_by_domain = defaultdict(lambda: {"n_sec": 0, "n_ph": 0, "ph_kind": Counter()})
    chunk_by_domain = defaultdict(list)
    chunk_by_tier = defaultdict(list)
    ph_chunk_by_tier = Counter()
    tier_chunk_total = Counter()
    ph_headings = Counter()
    sec_by_tier = Counter()
    headings_by_tier = defaultdict(Counter)

    for r in conn.execute("SELECT document_id, heading FROM sections"):
        d = docs.get(r["document_id"])
        if not d:
            continue
        key = d["domain"] or "(empty)"
        tier = tier_of(d["domain"], d["source_path"])
        kind = is_placeholder(r["heading"])
        sec_by_domain[key]["n_sec"] += 1
        sec_by_tier[tier] += 1
        headings_by_tier[tier][(r["heading"] or "").strip()[:30]] += 1
        if kind:
            sec_by_domain[key]["n_ph"] += 1
            sec_by_domain[key]["ph_kind"][kind] += 1
            ph_headings[r["heading"].strip()] += 1

    for r in conn.execute("SELECT document_id, length(plain_text) AS L, heading_path FROM chunks"):
        d = docs.get(r["document_id"])
        if not d:
            continue
        tier = tier_of(d["domain"], d["source_path"])
        chunk_by_domain[d["domain"] or "(empty)"].append(r["L"])
        chunk_by_tier[tier].append(r["L"])
        tier_chunk_total[tier] += 1
        if is_placeholder(r["heading_path"].split(" > ")[-1] if r["heading_path"] else ""):
            ph_chunk_by_tier[tier] += 1

    def chunk_stats(vals):
        if not vals:
            return {}
        return {"n": len(vals), "avg_chars": round(sum(vals) / len(vals), 1),
                "p50": pctl(vals, 0.5), "p90": pctl(vals, 0.9), "p99": pctl(vals, 0.99),
                "lt_100": sum(1 for v in vals if v < 100),
                "lt_200": sum(1 for v in vals if v < 200)}

    by_domain = {}
    for k, v in sorted(sec_by_domain.items(), key=lambda kv: -kv[1]["n_sec"]):
        by_domain[k] = {
            "n_sections": v["n_sec"],
            "n_placeholder_sections": v["n_ph"],
            "placeholder_ratio": round(v["n_ph"] / v["n_sec"], 3) if v["n_sec"] else 0.0,
            "placeholder_kinds": dict(v["ph_kind"]),
            "chunks": chunk_stats(chunk_by_domain.get(k, [])),
        }

    by_tier = {}
    for t in sorted(chunk_by_tier, key=lambda x: -len(chunk_by_tier[x])):
        n_t = tier_chunk_total[t]
        n_sec = sec_by_tier[t]
        hc = headings_by_tier[t]
        by_tier[t] = {
            "n_chunks": n_t,
            "n_sections": n_sec,
            "chunks_per_section": round(n_t / n_sec, 1) if n_sec else None,
            "distinct_headings": len(hc),
            "top_headings": hc.most_common(5),
            "placeholder_chunks": ph_chunk_by_tier[t],
            "placeholder_chunk_ratio": round(ph_chunk_by_tier[t] / n_t, 3) if n_t else 0.0,
            "chunk_len": chunk_stats(chunk_by_tier[t]),
        }

    out = {
        "description": "按 domain / corpus_tier 的章节与 chunk 质量分布；占位标题 = 元信息 / 配图N / 图表（pN OCR）/ 空标题",
        "placeholder_patterns": [p.pattern for _, p in PLACEHOLDER_PATTERNS],
        "by_domain": by_domain,
        "by_corpus_tier": by_tier,
        "top_placeholder_headings": ph_headings.most_common(20),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"by_tier": {k: {kk: vv for kk, vv in v.items() if kk not in ("chunk_len", "top_headings")}
                                  for k, v in by_tier.items()},
                      "top_placeholders": ph_headings.most_common(8)}, ensure_ascii=False, indent=2))
    print(f"-> {OUT}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
