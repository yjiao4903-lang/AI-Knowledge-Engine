# -*- coding: utf-8 -*-
"""P8-BENCH-01 题集独立校验（第二次验证：对照源内容，而非检索输出）。

职责：
  1. schema / 枚举 / 唯一 id / 禁止 heading 锚定；
  2. gold 解析：chunk_id 存在于 catalog、grade>=2、unresolved=0；
  3. **锚点复核**：生成时记录的 anchor_term 必须真实出现在 gold chunk 的源文本中；
  4. **源冻结复核**：source_hashes 的 sha256 与当前 catalog 一致（语料未漂移）；
  5. 反泄漏：Dev/Holdout 目标文档集不相交；cross_doc 的 gold 文档同属一个 split；
     九个 Legacy target 文档不得作为新题 gold；
  6. 分层/题型配额与护栏（单层 ≤35%、每层 ≥10%、OCR 覆盖）；
  7. Legacy 50 字节级冻结（sha256 与冻结值一致）；
  8. Holdout 密封：不得位于仓库内（除非显式 --allow-repo-holdout）。

输出：JSON 报告 + Markdown 覆盖表。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CATALOG = REPO / "data" / "catalog_full.db"
LEGACY_TARGETS = {"M04", "M05", "M06", "M07", "M09", "M10", "M16", "M18", "M22"}
LEGACY_FROZEN_SHA = "aa0412a24ccc30b6a0d75d97e4265b948b83bdb1c674db28f45eb17453973aea"
QUERY_TYPES = {"exact_entity", "exact_number", "semantic_thesis", "causal", "temporal",
               "long_tail", "cross_doc",
               # P8-BENCH-02 pilot families
               "numeric", "comparison", "mechanism", "entity_context", "multi_evidence"}
SOURCE_TYPES = {"flagship", "formal_report", "daily", "discussion", "image_material", "other"}
REQUIRED = ("id", "query", "query_type", "source_type", "split", "gold")
ANCHOR_RE = re.compile(r"anchor_term=(?:'([^']*)'|\"([^\"]*)\")")


def ro():
    c = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def anchor_of(it):
    m = ANCHOR_RE.search(it.get("notes", ""))
    return (m.group(1) or m.group(2)) if m else None


def load(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def sha_file(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify_split(conn, items, split, report):
    errs = []
    seen = set()
    per_doc = Counter()
    tier, qt, st = Counter(), Counter(), Counter()
    ocr = 0
    docs = set()
    for it in items:
        qid = it.get("id", "?")
        for f in REQUIRED:
            if f not in it:
                errs.append(f"{qid}: missing {f}")
        if qid in seen:
            errs.append(f"{qid}: duplicate id")
        seen.add(qid)
        if it.get("split") != split:
            errs.append(f"{qid}: split={it.get('split')} != {split}")
        if it.get("query_type") not in QUERY_TYPES:
            errs.append(f"{qid}: bad query_type {it.get('query_type')}")
        if it.get("source_type") not in SOURCE_TYPES:
            errs.append(f"{qid}: bad source_type {it.get('source_type')}")
        tier[it.get("corpus_tier")] += 1
        qt[it.get("query_type")] += 1
        st[it.get("source_type")] += 1
        ocr += 1 if it.get("ocr_derived") else 0
        gold = it.get("gold") or {}
        if "sections" in gold or "heading_contains" in json.dumps(gold, ensure_ascii=False):
            errs.append(f"{qid}: heading anchoring forbidden")
            continue
        term = anchor_of(it)
        rubric = (it.get("judging") or {}).get("rubric")
        req = [t for t in (rubric or {}).get("req", []) if t]
        broad2 = [t for t in (rubric or {}).get("broad2", []) if t]
        pats = [re.compile(p, re.I) for p in (rubric or {}).get("requires_any", [])]
        rel = 0
        for g in gold.get("chunks", []) or []:
            cid = g.get("chunk_id")
            row = conn.execute(
                "SELECT document_id, plain_text, heading_path, raw_markdown FROM chunks WHERE id=?",
                (cid,)).fetchone()
            if row is None:
                errs.append(f"{qid}: gold chunk unresolved {cid}")
                continue
            if g.get("grade", 0) >= 2:
                rel += 1
            docs.add(row["document_id"])
            per_doc[row["document_id"]] += 1
            blob = ((row["plain_text"] or "") + "\n" + (row["heading_path"] or "")
                    + "\n" + (row["raw_markdown"] or "")).lower()
            if rubric:
                if g.get("grade", 0) >= 3 and req and not all(t.lower() in blob for t in req):
                    errs.append(f"{qid}: gold grade3 fails rubric req: {cid}")
                if g.get("grade", 0) >= 3 and pats and not all(p.search(blob) for p in pats):
                    errs.append(f"{qid}: gold grade3 fails rubric predicate: {cid}")
                if g.get("grade", 0) == 2 and broad2 and not all(t.lower() in blob for t in broad2):
                    errs.append(f"{qid}: gold grade2 fails rubric broad2: {cid}")
            elif term and term.lower() not in blob:
                errs.append(f"{qid}: anchor_term {term!r} not found in gold chunk {cid}")
        if rel == 0:
            errs.append(f"{qid}: no grade>=2 gold")
        for sh in it.get("source_hashes", []) or []:
            r = conn.execute("SELECT sha256 FROM documents WHERE id=?", (sh["document_id"],)).fetchone()
            if r is None or r["sha256"] != sh["sha256"]:
                errs.append(f"{qid}: source hash drift for {sh['document_id']}")
            if sh["document_id"] in LEGACY_TARGETS:
                errs.append(f"{qid}: uses Legacy target doc {sh['document_id']}")
    n = len(items)
    report["splits"][split] = {
        "n": n, "errors": errs, "pass": not errs,
        "by_tier": dict(sorted(tier.items())), "by_query_type": dict(sorted(qt.items())),
        "by_source_type": dict(sorted(st.items())),
        "max_tier_share": round(max(tier.values()) / n, 4) if n else 0,
        "min_tier_share": round(min(tier.values()) / n, 4) if n else 0,
        "ocr_derived": ocr, "distinct_gold_docs": len(docs),
        "max_queries_per_doc": max(per_doc.values()) if per_doc else 0,
        "target_docs": sorted(docs),
    }
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--development", required=True)
    ap.add_argument("--holdout", required=True)
    ap.add_argument("--legacy", default=str(REPO / "docs/p8_review/benchmark/legacy_v1/golden_queries.jsonl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    ap.add_argument("--allow-repo-holdout", action="store_true")
    a = ap.parse_args()

    conn = ro()
    dev_p, hold_p, leg_p = Path(a.development), Path(a.holdout), Path(a.legacy)
    dev, hold = load(dev_p), load(hold_p)
    report = {"legacy": {}, "splits": {}, "leakage": {}, "sealing": {}}

    verify_split(conn, dev, "development", report)
    verify_split(conn, hold, "holdout", report)

    dev_docs = set(report["splits"]["development"]["target_docs"])
    hold_docs = set(report["splits"]["holdout"]["target_docs"])
    overlap = sorted(dev_docs & hold_docs)
    report["leakage"] = {"dev_target_docs": len(dev_docs), "holdout_target_docs": len(hold_docs),
                         "overlap": overlap, "pass": not overlap}

    # 密封：holdout 不得在仓库内
    try:
        hold_p.resolve().relative_to(REPO.resolve())
        in_repo = True
    except ValueError:
        in_repo = False
    report["sealing"] = {"holdout_path": str(hold_p), "holdout_in_repo": in_repo,
                         "pass": (not in_repo) or a.allow_repo_holdout,
                         "sha256": sha_file(hold_p), "dev_sha256": sha_file(dev_p)}

    # Legacy 冻结
    leg_sha = sha_file(leg_p)
    report["legacy"] = {"path": str(leg_p), "sha256": leg_sha,
                        "expected": LEGACY_FROZEN_SHA, "n": len(load(leg_p)),
                        "pass": leg_sha == LEGACY_FROZEN_SHA}

    # 覆盖护栏
    for sp in ("development", "holdout"):
        s = report["splits"][sp]
        s["tier_guardrail_pass"] = s["max_tier_share"] <= 0.35 and s["min_tier_share"] >= 0.10
        s["ocr_share"] = round(s["ocr_derived"] / s["n"], 4) if s["n"] else 0

    report["pass"] = (report["splits"]["development"]["pass"] and report["splits"]["holdout"]["pass"]
                      and report["leakage"]["pass"] and report["sealing"]["pass"]
                      and report["legacy"]["pass"])

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": report["pass"],
                      "dev": {k: report["splits"]["development"][k] for k in ("n", "pass", "max_tier_share", "min_tier_share", "ocr_share", "errors")},
                      "holdout": {k: report["splits"]["holdout"][k] for k in ("n", "pass", "max_tier_share", "min_tier_share", "ocr_share", "errors")},
                      "leakage": report["leakage"], "sealing": {k: report["sealing"][k] for k in ("holdout_in_repo", "pass")},
                      "legacy": {k: report["legacy"][k] for k in ("n", "pass")}}, ensure_ascii=False, indent=2))

    if a.md:
        lines = ["# P8 混合题集覆盖与校验报告", "",
                 f"- Development: n={report['splits']['development']['n']} pass={report['splits']['development']['pass']}",
                 f"- Holdout: n={report['splits']['holdout']['n']} pass={report['splits']['holdout']['pass']} (sealed, in_repo={in_repo})",
                 f"- Legacy 50: n={report['legacy']['n']} frozen_sha_ok={report['legacy']['pass']}",
                 f"- Leakage (dev∩holdout target docs): {len(overlap)}",
                 "", "## 分层覆盖", "", "| tier | dev | dev% | holdout | holdout% |", "|---|---|---|---|---|"]
        tiers = sorted(set(report["splits"]["development"]["by_tier"]) | set(report["splits"]["holdout"]["by_tier"]))
        for t in tiers:
            d = report["splits"]["development"]; h = report["splits"]["holdout"]
            lines.append(f"| {t} | {d['by_tier'].get(t,0)} | {d['by_tier'].get(t,0)/d['n']:.1%} | "
                         f"{h['by_tier'].get(t,0)} | {h['by_tier'].get(t,0)/h['n']:.1%} |")
        lines += ["", "## 题型覆盖", "", "| query_type | dev | holdout |", "|---|---|---|"]
        for t in sorted(set(report["splits"]["development"]["by_query_type"]) | set(report["splits"]["holdout"]["by_query_type"])):
            lines.append(f"| {t} | {report['splits']['development']['by_query_type'].get(t,0)} | "
                         f"{report['splits']['holdout']['by_query_type'].get(t,0)} |")
        Path(a.md).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("wrote", a.md)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
