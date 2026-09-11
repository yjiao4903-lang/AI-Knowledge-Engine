# -*- coding: utf-8 -*-
"""P8-1 Benchmark 校验器（只读 catalog；题集本身待人工按领域判断编写）。

职责（可自动化的那一半）：
  1. schema 必填字段 / split 值校验；
  2. gold 锚定校验：Development/Holdout **禁止 heading_contains**，必须 chunk_ids / content_anchors；
  3. 解析到 catalog，`unresolved` 必须为 0，且每题至少一个 grade>=2；
  4. id 唯一；
  5. `--suggest-chunks --doc <id> [--section <sid>]`：列出候选 chunk_id 供人工选题（不做领域判断）。

用法：
  python pipeline/p8_bench_validate.py --questions _golden/benchmark/development_v1/questions_v1.jsonl --split development
  python pipeline/p8_bench_validate.py --suggest-chunks --doc M04 --limit 20
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

E = Path(r"E:\研报提取资料库")
CATALOG = r"D:/AI-Knowledge-Engine/data/catalog_full.db"
REQUIRED = ("id", "query", "query_type", "source_type", "split", "gold")
QUERY_TYPES = {"exact_entity", "exact_number", "semantic_thesis", "causal", "temporal", "long_tail", "cross_doc"}
SOURCE_TYPES = {"flagship", "formal_report", "daily", "discussion", "image_material", "other"}


def ro() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def resolve(conn, gold):
    hits = []
    if gold.get("chunks"):
        for it in gold["chunks"]:
            r = conn.execute("SELECT id FROM chunks WHERE id=?", (it["chunk_id"],)).fetchone()
            if r:
                hits.append((it["chunk_id"], it["grade"]))
    for it in gold.get("content_anchors", []) or []:
        rows = conn.execute("SELECT id FROM chunks WHERE document_id=? AND plain_text LIKE ? LIMIT 5",
                            (it["document_id"], f"%{it['anchor_contains']}%")).fetchall()
        for r in rows:
            hits.append((r["id"], it["grade"]))
    return hits


def validate(path: Path, split: str) -> int:
    conn = ro()
    qs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    errs, seen = [], set()
    tcount, scount = {}, {}
    for q in qs:
        qid = q.get("id", "?")
        for f in REQUIRED:
            if f not in q:
                errs.append(f"{qid}: 缺字段 {f}")
        if qid in seen:
            errs.append(f"{qid}: id 重复")
        seen.add(qid)
        if q.get("split") != split:
            errs.append(f"{qid}: split={q.get('split')} != {split}")
        if q.get("query_type") not in QUERY_TYPES:
            errs.append(f"{qid}: query_type 非法 {q.get('query_type')}")
        if q.get("source_type") not in SOURCE_TYPES:
            errs.append(f"{qid}: source_type 非法 {q.get('source_type')}")
        tcount[q.get("query_type")] = tcount.get(q.get("query_type"), 0) + 1
        scount[q.get("source_type")] = scount.get(q.get("source_type"), 0) + 1
        gold = q.get("gold") or {}
        if "sections" in gold or "heading_contains" in json.dumps(gold, ensure_ascii=False):
            errs.append(f"{qid}: 新题集禁止 heading 锚定，必须用 chunks/content_anchors")
            continue
        hits = resolve(conn, gold)
        rel = [h for h in hits if h[1] >= 2]
        if not hits:
            errs.append(f"{qid}: gold unresolved（0 命中）")
        elif not rel:
            errs.append(f"{qid}: gold 无 grade>=2")
    conn.close()
    print(json.dumps({"file": str(path), "split": split, "n": len(qs), "unresolved": sum(1 for e in errs if "unresolved" in e),
                      "errors": errs, "query_type_dist": tcount, "source_type_dist": scount,
                      "pass": not errs}, ensure_ascii=False, indent=2))
    return 0 if not errs else 1


def suggest(doc: str, section: str | None, limit: int) -> int:
    conn = ro()
    sql = ("SELECT c.id, c.section_id, c.heading_path, substr(c.plain_text,1,80) AS head, length(c.plain_text) L "
           "FROM chunks c WHERE c.document_id=?")
    params = [doc]
    if section:
        sql += " AND c.section_id=?"
        params.append(section)
    sql += " ORDER BY c.start_line LIMIT ?"
    params.append(limit)
    for r in conn.execute(sql, params):
        print(json.dumps(dict(r), ensure_ascii=False))
    conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions")
    ap.add_argument("--split", default="development", choices=["legacy", "development", "holdout"])
    ap.add_argument("--suggest-chunks", action="store_true")
    ap.add_argument("--doc"), ap.add_argument("--section"), ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    if a.suggest_chunks:
        return suggest(a.doc, a.section, a.limit)
    if not a.questions:
        print("ERROR: --questions required")
        return 2
    return validate(Path(a.questions), a.split)


if __name__ == "__main__":
    raise SystemExit(main())
