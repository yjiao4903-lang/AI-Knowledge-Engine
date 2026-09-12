# -*- coding: utf-8 -*-
"""P8-CORPUS-01 · C 阶段：确定性 heading/title metadata recovery（shadow 专用）。

对 subset_manifest 中的外资研报文档：
  1. 从原始 PDF（pymupdf dict 模式）抽取逐行字体特征；
  2. 判定 heading 候选（字号 > body、短行、非 bullet、非重复页眉页脚、非纯数字/日期）；
  3. 用归一化文本匹配把 heading 注入 markdown 副本的对应行前（## / ### 两级）；
  4. 全程不改正文文本、不改 front matter、不动原文件——只写 shadow root 副本。

确定性：无随机源；同一 PDF+md 输入字节级可复现。
"""
from __future__ import annotations
import json, re, os, sys, hashlib
from collections import Counter, defaultdict
import pymupdf

SRC_DIR = r"D:\DataMigration\180K知识星球\data\28888222154481_180K Research\files"
AUDIT = r"D:/AIKE-local-a-corpus01/shadow/audit/foreign_research_audit.json"
MANIFEST = r"D:/AIKE-local-a-corpus01/shadow/audit/subset_manifest.json"
OUT_ROOT = r"D:/AIKE-local-a-corpus01/shadow/root_shadow/外资研报"

MAX_HEADING_CHARS = 80
BULLET_RE = re.compile(r"^\s*[•·▪–\-]\s+")
NUMERIC_RE = re.compile(r"^[\s\d.,%$€£()/_:-]+$")
DATE_RE = re.compile(r"^\s*(\d{1,2}[-/][A-Za-z]{3}|\d{4}年|\w{3} \d{1,2},? \d{4}|on \d{2}-\w{3}-\d{4})")
TERMINAL_RE = re.compile(r"[.,;:!?，。；：！？]$|的[。]$")  # 结尾句读（heading 不应带）
SOURCE_RE = re.compile(r"^\s*(Source|资料来源|来源)\s*[:：]")

def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()

def page_lines(page):
    """[(text, max_size, bold, x0, y0, first_span_x1, block_nlines)] 逐行。"""
    out = []
    d = page.get_text("dict")
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        nlines = len([l for l in b["lines"] if any(s["text"].strip() for s in l["spans"])])
        for l in b["lines"]:
            spans = [s for s in l["spans"] if s["text"].strip()]
            if not spans:
                continue
            txt = "".join(s["text"] for s in l["spans"]).strip()
            if not txt:
                continue
            first = l["spans"][0]
            out.append((txt, max(s["size"] for s in spans),
                        any(s["flags"] & 16 for s in spans),
                        l["bbox"][0], l["bbox"][1], first["bbox"][2], nlines))
    return out

def recover(md_path: str):
    fm = {}
    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()
    m = re.match(r"^---\r?\n(.*?)\r?\n---", md_text, re.S)
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"')
    src_file = fm.get("source_file", "")
    pdf_path = os.path.join(SRC_DIR, os.path.basename(src_file))
    if not os.path.exists(pdf_path):
        return None, f"PDF missing: {pdf_path}"

    doc = pymupdf.open(pdf_path)
    # body size = 字符数最多的字号
    size_chars = Counter()
    for page in doc:
        for txt, sz, bold, x0, y0, x1, _nl in page_lines(page):
            size_chars[round(sz, 1)] += len(txt)
    if not size_chars:
        return None, "empty pdf"
    body = size_chars.most_common(1)[0][0]

    # 逐页 heading 候选；bullet 块用几何缩进状态机排除（续行 x0 >= bullet 文本起点）
    per_page = []
    h1_norm = None
    m1 = re.match(r"^#\s+(.+)$", md_text, re.M)
    if m1:
        h1_norm = norm(m1.group(1))
    title_norm = norm(fm.get('title', ''))
    for pno, page in enumerate(doc):
        lines_ = page_lines(page)
        cands = []
        bullet_text_x0 = None
        for txt, sz, bold, x0, y0, first_x1, nl in lines_:
            stripped = txt.strip()
            if BULLET_RE.match(txt):
                bullet_text_x0 = first_x1  # bullet 标记后的文本起点
                continue
            if bullet_text_x0 is not None:
                if x0 >= bullet_text_x0 - 2.0:
                    continue  # bullet 续行（同块缩进）
                bullet_text_x0 = None  # 反缩进 -> 块结束
            if nl > 1:
                continue  # 多行 block = 换行段落/bullet 块，非 heading
            if sz < body + 1.0 and not (bold and sz >= body + 1.0):
                continue
            if len(txt) > MAX_HEADING_CHARS:
                continue
            if NUMERIC_RE.match(txt) or DATE_RE.match(txt):
                continue
            if TERMINAL_RE.search(stripped) and not stripped.endswith(':') and not stripped.endswith('：'):
                continue
            if SOURCE_RE.match(txt):
                continue
            if len(norm(txt)) < 2:
                continue
            if title_norm and norm(txt) == title_norm:
                continue
            if h1_norm and norm(txt) == h1_norm:
                continue
            cands.append((txt, round(sz, 1), bold, x0, y0))
        per_page.append(cands)

    # 页眉/页脚抑制：同一文本出现在 >=3 页；出现 2 页只保留首次
    occur = defaultdict(list)
    for pno, cands in enumerate(per_page):
        for txt, sz, bold, y0, y1 in cands:
            occur[norm(txt)].append((pno, sz, bold))
    drop = {k for k, v in occur.items() if len({p for p, _, _ in v}) >= 3}

    # markdown 行索引：page marker -> 行号
    lines = md_text.splitlines()
    page_marker_idx = {}
    for i, ln in enumerate(lines):
        mm = re.match(r"<!-- page: (\d+) -->", ln.strip())
        if mm:
            page_marker_idx[int(mm.group(1))] = i
    md_pages = sorted(page_marker_idx)
    def page_span(pno):
        """pdf 0-based pno 对应 markdown 行区间 [start, end)。"""
        key = pno + 1
        if key not in page_marker_idx:
            return None
        start = page_marker_idx[key]
        nxt = [page_marker_idx[p] for p in md_pages if p > key]
        end = min(nxt) if nxt else len(lines)
        return start, end

    # level 映射：字号降序分层
    cand_sizes = sorted({sz for cands in per_page for _, sz, _, _, _ in cands}, reverse=True)

    injections = []   # (line_idx, level, text)
    stats = Counter()
    used_lines = set()
    seen_heading_once = set()
    for pno, cands in enumerate(per_page):
        span = page_span(pno)
        seen_in_doc = set()
        for txt, sz, bold, y0, y1 in cands:
            key = norm(txt)
            if key in drop:
                stats["drop_repeat"] += 1
                continue
            if key in seen_heading_once:
                stats["drop_dup2"] += 1
                continue
            seen_heading_once.add(key)
            if span is None:
                stats["no_page_region"] += 1
                continue
            start, end = span
            target = None
            for i in range(start, end):
                if i in used_lines:
                    continue
                if norm(lines[i]) == key:
                    target = i
                    break
            if target is None:
                stats["no_md_match"] += 1
                continue
            if sz >= body + 3.0 or (cand_sizes and sz == cand_sizes[0]):
                level = 2
            else:
                level = 3
            injections.append((target, level, txt))
            used_lines.add(target)
            seen_in_doc.add(key)
            stats["injected"] += 1
    doc.close()

    out_lines = lines[:]
    for target, level, txt in sorted(injections, reverse=True):
        prefix = "#" * level
        clean = re.sub(r"\s+", " ", txt).strip()
        out_lines.insert(target, f"{prefix} {clean}")
    return ("\n".join(out_lines) + ("\n" if md_text.endswith("\n") else "")), dict(stats)

def main():
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    audit = {r["document_id"]: r for r in json.load(open(AUDIT, encoding="utf-8"))}
    os.makedirs(OUT_ROOT, exist_ok=True)
    report = []
    for did in manifest["fr_repair_doc_ids"]:
        rec = audit[did]
        md_path = rec["source_path"]
        new_text, stats = recover(md_path)
        if new_text is None:
            report.append({"document_id": did, "status": "skip", "reason": stats})
            continue
        out_path = os.path.join(OUT_ROOT, os.path.basename(md_path))
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
        report.append({
            "document_id": did,
            "status": "ok",
            "out_path": out_path,
            "out_sha256": sha(out_path),
            "src_sha256": rec["sha256"],
            "stats": stats,
        })
    with open(r"D:/AIKE-local-a-corpus01/shadow/audit/repair_report.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    ok = [r for r in report if r["status"] == "ok"]
    inj = sum(r["stats"].get("injected", 0) for r in ok)
    print(json.dumps({
        "docs_ok": len(ok), "docs_skip": len(report) - len(ok),
        "injected_headings_total": inj,
        "avg_per_doc": round(inj / max(1, len(ok)), 2),
        "drop_repeat": sum(r["stats"].get("drop_repeat", 0) for r in ok),
        "drop_dup2": sum(r["stats"].get("drop_dup2", 0) for r in ok),
        "no_md_match": sum(r["stats"].get("no_md_match", 0) for r in ok),
        "no_page_region": sum(r["stats"].get("no_page_region", 0) for r in ok),
    }, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
