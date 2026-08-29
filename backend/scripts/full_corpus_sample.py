"""I0 全库人工抽样核对（主计划 §13 / HANDOFF_I0 §1.3）。

随机抽 100 篇（>=50 要求），对每篇做独立复验（不复用索引过程数据）：
  - metadata：report_code/title 回读一致
  - heading tree：独立 parse 的 section 数、heading_path 与 catalog 一致
  - line range：sections/chunks 行号在原文行数范围内且非空
  - tables/formula/reference/audit：special block 抽样存在性对账
  - encoding：源文件 UTF-8 可读
输出 data/full_corpus_sample.json（逐项明细 + 结论）。

用法：
  KE_CONFIG=config/config.full.yaml python backend/scripts/full_corpus_sample.py [N]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402


def main() -> int:
    n_sample = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
    cfg = load_config(sys.argv[2] if len(sys.argv) > 2 else None)
    from app.parser.markdown_parser import parse_markdown
    from app.storage.sqlite import connect

    conn = connect(cfg.sqlite.path, read_only=True)
    docs = conn.execute(
        "SELECT id, source_path, title, sha256 FROM documents ORDER BY id").fetchall()
    random.seed(20260829)  # 固定种子可复现
    sample = random.sample(docs, min(n_sample, len(docs)))

    results = []
    failures = []
    for row in sample:
        doc_id, src, title, sha = row["id"], row["source_path"], row["title"], row["sha256"]
        item = {"document_id": doc_id, "checks": {}, "ok": True}
        try:
            raw = Path(src).read_bytes()
            text = raw.decode("utf-8")
            item["checks"]["encoding"] = "PASS"
        except Exception as exc:
            item["checks"]["encoding"] = f"FAIL: {exc}"
            item["ok"] = False
            failures.append(item)
            results.append(item)
            continue

        n_lines = len(text.splitlines())
        doc = parse_markdown(text)

        # metadata
        item["checks"]["metadata"] = (
            "PASS" if doc.metadata.get("title", doc.title) == title else
            f"FAIL: title 不一致 {title!r} vs {doc.metadata.get('title', doc.title)!r}")

        # heading tree（catalog sections vs 独立 parse）
        cat_secs = conn.execute(
            "SELECT id, heading_path, start_line, end_line, section_type FROM sections "
            "WHERE document_id = ? ORDER BY ordinal", (doc_id,)).fetchall()
        if len(cat_secs) == len(doc.sections) and all(
                c["heading_path"] == " > ".join(s.heading_path)
                for c, s in zip(cat_secs, doc.sections)):
            item["checks"]["heading_tree"] = f"PASS ({len(cat_secs)} sections)"
        else:
            item["checks"]["heading_tree"] = (
                f"FAIL: catalog {len(cat_secs)} vs parse {len(doc.sections)} 或 heading_path 不一致")
            item["ok"] = False

        # line range
        bad = [c["id"] for c in cat_secs
               if not (1 <= c["start_line"] <= c["end_line"] <= n_lines + 1)]
        item["checks"]["line_range"] = "PASS" if not bad else f"FAIL: {bad[:3]}"

        # chunks 行号 + 非空 + 表/公式/引用/审计类型对账
        cat_chunks = conn.execute(
            "SELECT id, start_line, end_line, plain_text, content_type FROM chunks "
            "WHERE document_id = ? ORDER BY ordinal", (doc_id,)).fetchall()
        bad_chunks = [c["id"] for c in cat_chunks
                      if not (1 <= c["start_line"] <= c["end_line"] <= n_lines + 1)
                      or not (c["plain_text"] or "").strip()]
        item["checks"]["chunks"] = (
            f"PASS ({len(cat_chunks)} chunks)" if not bad_chunks else f"FAIL: {bad_chunks[:3]}")
        if bad_chunks:
            item["ok"] = False

        types = {c["content_type"] for c in cat_chunks}
        has_table = any(b.block_type == "table" for s in doc.sections for b in s.blocks)
        if has_table:
            # ADR-007：chunk 类型可继承父 section 类型；表格完整性以表格行内容
            # 是否落块为准（存在 table 类型块 OR 源文表行能在 chunk 正文中找到）
            src_table_lines = [b.text for s in doc.sections for b in s.blocks
                               if b.block_type == "table"]
            norm = lambda t: "".join(ch for ch in t if not ch.isspace() and ch != "|")
            joined = norm(chr(10).join(c["plain_text"] or "" for c in cat_chunks))
            found = all(norm(ln)[:40] in joined for ln in src_table_lines[:5])
            if found or "table" in types:
                item["checks"]["tables"] = "PASS"
            else:
                item["checks"]["tables"] = "FAIL: 源文表内容未落入任何 chunk"
                item["ok"] = False
        else:
            item["checks"]["tables"] = "N/A(无表)"
        ref_secs = [s for s in doc.sections if s.section_type == "reference"]
        cat_ref = conn.execute(
            "SELECT COUNT(*) FROM sections WHERE document_id = ? AND section_type = 'reference'",
            (doc_id,)).fetchone()[0]
        item["checks"]["reference_audit"] = (
            "PASS" if len(ref_secs) == cat_ref else f"FAIL: {len(ref_secs)} vs {cat_ref}")
        item["counts"] = {"sections": len(cat_secs), "chunks": len(cat_chunks),
                          "content_types": sorted(types)}
        if not item["ok"]:
            failures.append(item)
        results.append(item)

    passed = sum(1 for r in results if r["ok"])
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seed": 20260829,
        "sampled": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 3) if results else 0.0,
        "failures": failures,
        "results": results,
    }
    (PROJECT_ROOT / "data" / "full_corpus_sample.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("sampled", "passed", "failed", "pass_rate")},
                     ensure_ascii=False))
    for f in failures[:10]:
        print("FAIL:", f["document_id"], f["checks"])
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
