# -*- coding: utf-8 -*-
"""P8-BENCH-02 pilot：claim/context-specific 出题 + 分级相关性金标（确定性）。

与 #36 的关键区别
-----------------
1. **查询特异性**：每题由源 chunk 中的具体事实/主张出发，包含 ≥2 个判别项
   （实体+单位/期间/第二实体/机制），不再使用 "报告中 X 怎么样" 类宽泛实体提示。
2. **多 chunk 分级金标**：用显式 rubric 在**全语料**枚举 grade-2/3 正例（required token 交集
   + 可选答案 token / 谓词），而非单一任意 chunk；正例过多则收紧或拒题。
3. **可复核**：每题记录 rubric（判别 token、答案 token、谓词）与 rejected 原因；
   检索 4 视图只用于**候选池/FN 审计**（见 p8_bench_pool.py），不用于调参。

家族：numeric / comparison / mechanism / temporal / entity_context / multi_evidence。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p8_bench_build as b  # noqa: E402  复用词典/实体抽取/分层

REPO = Path(__file__).resolve().parents[3]
CATALOG = REPO / "data" / "catalog_full.db"
SEED = "p8-bench-02-pilot-20260911"
LEGACY_TARGETS = b.LEGACY_TARGETS

FAMILIES = ["numeric", "comparison", "mechanism", "temporal", "entity_context", "multi_evidence"]
FAMILY_QUOTA = {"development": {"numeric": 12, "comparison": 9, "mechanism": 12,
                                "temporal": 10, "entity_context": 5, "multi_evidence": 12},
                "holdout": {"numeric": 8, "comparison": 6, "mechanism": 8,
                            "temporal": 7, "entity_context": 3, "multi_evidence": 8}}
TIER_QUOTA = {"development": {"flagship": 12, "broker_report": 12, "daily_report": 10,
                              "trading_desk": 6, "research_media": 10, "discussion": 10},
              "holdout": {"flagship": 8, "broker_report": 8, "daily_report": 7,
                          "trading_desk": 4, "research_media": 7, "discussion": 6}}
MAX_POS = 25
MAX_GRADE3 = 8
TARGETS = {"development": 60, "holdout": 40}
# 宏观/指数类：不作为 comparison 的一侧（避免 FOMC vs Fed、个股 vs 指数等无意义配对）
MACRO = {"FOMC", "Fed", "CPI", "GDP", "PMI", "ECB", "BOJ", "PBOC", "NFP", "ISM", "PPI", "YCC",
         "SPX", "NDX", "VIX", "KOSPI", "Nikkei", "ETF", "HSI", "CSI", "SOFR", "LIBOR", "HIBOR"}
NEUTRAL_UNITS = {"%", "％", "pct", "个百分点", "bp", "bps"}
# 指标名词（用于把"相关指标"具体化为"营收增速/出货量/毛利率"等，提升查询特异性）
METRIC_NOUNS = ["营收增速", "营收", "收入", "净利润", "营业利润", "利润", "毛利率", "净利率",
                "营业利润率", "增速", "同比", "环比", "出货量", "交付量", "销量", "产量", "产能",
                "装机量", "订单", "积压订单", "库存", "价格", "均价", "市占率", "渗透率",
                "资本开支", "指引", "目标价", "评级", "算力", "功耗", "良率", "成本",
                "revenue", "margin", "growth", "shipment", "shipments", "pricing", "backlog",
                "capex", "EPS", "FCF", "ASP"]
CATEGORY = {"CPU", "GPU", "SoC", "DRAM", "NAND", "HBM", "Cloud", "SSD", "ASIC", "FPGA", "IP",
            "EDA", "EUV", "DUV", "AI", "IoT", "5G", "6G", "PC", "Server", "Memory", "Datacenter"}


def metric_near(text: str, start: int, end: int) -> str | None:
    """在数值附近寻找指标名词。"""
    best = None
    for noun in METRIC_NOUNS:
        i = text.rfind(noun, max(0, start - 50), start)
        if i != -1 and (best is None or len(noun) > len(best)):
            best = noun
            continue
        j = text.find(noun, end, end + 25)
        if j != -1 and (best is None or len(noun) > len(best)):
            best = noun
    return best

NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
                 r"(%|％|个百分点|pct|bp|bps|倍|万亿元|亿元|亿美元|万美元|万|亿|"
                 r"nm|um|mm|GW|GWh|MW|kW|TWh|GB|TB|PB|TFLOPS|TOPS|美元|元|ms|ns|GB/s|TB/s)")
DATE = re.compile(r"(?<![\d/年])(20\d{2}\s*(?:[-/年\.]\s*\d{1,2}(?:\s*[-/月\.]\s*\d{1,2})?)?|"
                  r"Q[1-4]\s*[-/]?\s*20\d{2}|20\d{2}\s*Q[1-4])(?![\d/])")
CAUSAL = re.compile(r"(因为|由于|导致|因此|使得|驱动|原因是|之所以|because|due to|driven by|led to)")
CHANGE = re.compile(r"(增长|下降|提升|下滑|上调|下调|收缩|扩张|放量|减产|扩产|涨价|跌价|"
                    r"创新高|创新低|恶化|改善|调整|达到|降至|升至|突破|反弹|回落)")
UNIT_NAME = b.UNIT_NAME


def ro():
    c = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def unit_phrase(u: str) -> str:
    if not u or u in NEUTRAL_UNITS:
        return "相关指标"
    return UNIT_NAME.get(u, "数值")


def has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def distinct_tokens(text: str) -> list[str]:
    return sorted(set(b.entity_terms(text)))


def first_num(text: str):
    m = NUM.search(text)
    return (m.group(1), m.group(2)) if m else (None, None)


def first_date(text: str):
    m = DATE.search(text)
    if not m:
        return None
    ym = re.search(r"(20\d{2})", m.group(1))
    if ym and 2015 <= int(ym.group(1)) <= 2028:
        return m.group(1).strip()
    return None


def author(family: str, tier: str, doc: dict, df: dict):
    """返回 (query, rubric, meta) 或 None。

    rubric.req = grade-3 必需 token（含选择性数值答案）；broad2 = grade-2 宽 token（可选、有界）；
    requires_any = grade-3 还需命中的谓词（如因果连接词）。
    """
    for c in doc["chunks"]:
        text = c["text"]
        ents = distinct_tokens(text)
        val, unit = first_num(text)
        sv = selective_value(val)
        period = first_date(text)
        if family == "numeric":
            e1 = _pick(ents, df, 2, 400)
            nm = NUM.search(text)
            if not (e1 and sv and nm):
                continue
            metric = metric_near(text, nm.start(), nm.end())
            if not metric:
                continue  # 无指标名词 -> 查询过于含糊，拒题
            q = (f"报告中 {period} 前后 {e1} 的{metric}是多少？" if period
                 else f"报告中 {e1} 的{metric}是多少？")
            rubric = {"req": [e1, sv], "broad2": [], "requires_any": []}
            return q, rubric, {"entity": e1, "unit": unit, "value": val,
                               "period": period, "metric": metric}
        if family == "comparison":
            if len(ents) < 2:
                continue
            e1, e2 = _pick_pair(ents, df, text)
            if not (e1 and e2) or e1 in MACRO or e2 in MACRO or e1 in CATEGORY or e2 in CATEGORY:
                continue
            if e1[0].islower() or e2[0].islower():
                continue
            hd = b.good_heading(c["heading_path"], df)
            up = (UNIT_NAME.get(unit) if unit in UNIT_NAME and unit not in NEUTRAL_UNITS
                  else (hd if has_cjk(hd) else "相关指标"))
            q = f"报告如何比较 {e1} 与 {e2} 在{up}上的差异？"
            req = [e1, e2, sv] if sv else [e1, e2]
            rubric = {"req": req, "broad2": [], "requires_any": []}
            return q, rubric, {"entity": e1, "entity2": e2, "dim": up}
        if family == "mechanism":
            if not CAUSAL.search(text):
                continue
            e1 = _pick(ents, df, 2, 400)
            if not e1:
                continue
            causal = [r"(因为|由于|导致|因此|使得|驱动|because|due to|driven by)"]
            metric = next((n for n in METRIC_NOUNS if n in text), None)
            if sv:
                q = f"报告认为是什么机制导致 {e1} 的{metric or '相关指标'}变化？"
                rubric = {"req": [e1, sv], "broad2": [], "requires_any": causal}
                return q, rubric, {"entity": e1, "value": sv, "unit": unit, "metric": metric}
            if period:
                q = f"报告认为 {period} 前后 {e1} 的变化主要由什么机制驱动？"
                rubric = {"req": [e1, period], "broad2": [], "requires_any": causal}
                return q, rubric, {"entity": e1, "period": period}
            continue
        if family == "temporal":
            e1 = _pick(ents, df, 2, 400)
            if not (period and e1):
                continue
            if sv:
                q = f"{period} 前后 {e1} 的{unit_phrase(unit) if unit else '数值'}出现了什么变化？"
                rubric = {"req": [period, e1, sv], "broad2": [period, e1], "requires_any": []}
                return q, rubric, {"entity": e1, "period": period, "value": sv, "unit": unit}
            ch = CHANGE.search(text)
            if not ch:
                continue
            q = f"{period} 前后 {e1} 出现了哪些变化？"
            rubric = {"req": [period, e1, ch.group(1)], "broad2": [period, e1], "requires_any": []}
            return q, rubric, {"entity": e1, "period": period, "change": ch.group(1)}
        if family == "entity_context":
            e1 = _pick(ents, df, 2, 120)
            ctx = b.good_heading(c["heading_path"], df)
            if not (e1 and ctx) or ctx == e1 or not has_cjk(ctx) or not (4 <= len(ctx) <= 16):
                continue
            q = f"报告如何描述 {e1} 在「{ctx}」中的作用？"
            rubric = {"req": [e1, ctx], "broad2": [], "requires_any": []}
            return q, rubric, {"entity": e1, "context": ctx}
        if family == "multi_evidence":
            e1 = _pick(ents, df, 2, 400)
            if not (period and e1):
                continue
            if sv:
                q = f"报告用哪些证据说明 {period} 前后 {e1} 的{unit_phrase(unit) if unit else '数值'}变化？"
                rubric = {"req": [period, e1, sv], "broad2": [period, e1], "requires_any": []}
                return q, rubric, {"entity": e1, "period": period, "value": sv, "unit": unit}
            ch = CHANGE.search(text)
            if not ch:
                continue
            q = f"报告用哪些证据说明 {period} 前后 {e1} 的变化？"
            rubric = {"req": [period, e1, ch.group(1)], "broad2": [period, e1], "requires_any": []}
            return q, rubric, {"entity": e1, "period": period, "change": ch.group(1)}
    return None


def _pick(ents, df, lo, hi):
    cands = [w for w in ents if lo <= df.get(w, 1) <= hi]
    cands.sort(key=lambda w: (df.get(w, 1), -len(w), w))
    return cands[0] if cands else None


def _pick_pair(ents, df, text):
    cands = [w for w in ents if 2 <= df.get(w, 1) <= 800]
    cands.sort(key=lambda w: (-len(w), w))
    if len(cands) < 2:
        return None, None
    # 取出现位置最早的两个不同实体，保证同段可比
    pos = sorted(((text.find(w), w) for w in cands), key=lambda x: (x[0], x[1]))
    seen = []
    for _, w in pos:
        if w not in seen:
            seen.append(w)
        if len(seen) == 2:
            break
    return (seen[0], seen[1]) if len(seen) == 2 else (None, None)


def selective_value(val: str | None) -> str | None:
    """数值答案 token 必须有足够选择性（≥2 位有效数字或含小数），否则不用作判别项。"""
    if not val:
        return None
    v = val.replace(",", "")
    if "." in v or len(v) >= 2:
        return val
    return None


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_POS_CACHE: dict[tuple, dict] = {}


def enumerate_tokens(conn, tokens, limit=400):
    key = tuple(sorted(tokens))
    if key in _POS_CACHE:
        return _POS_CACHE[key]
    toks = sorted(tokens, key=lambda t: -len(t))  # 长 token 更稀有，先过滤
    clauses = " AND ".join(["lower(plain_text) LIKE ? ESCAPE '\\'"] * len(toks))
    params = [f"%{_like_escape(t.lower())}%" for t in toks]
    rows = conn.execute(
        f"SELECT id, document_id, plain_text, heading_path FROM chunks WHERE {clauses} LIMIT ?",
        (*params, limit)).fetchall()
    _POS_CACHE[key] = {r["id"]: (r["document_id"],
                                 ((r["plain_text"] or "") + "\n" + (r["heading_path"] or "")).lower())
                       for r in rows}
    return _POS_CACHE[key]


def enumerate_positives(conn, rubric):
    """grade3 = 命中全部 req（+谓词）；grade2 = 命中 broad2 且非 grade3（若 broad2 有界）。"""
    req = [t for t in rubric.get("req", []) if t]
    if not req:
        return {}
    pats = [re.compile(p, re.I) for p in rubric.get("requires_any", [])]
    out = {}
    for cid, (doc_id, blob) in enumerate_tokens(conn, req).items():
        if all(p.search(blob) for p in pats):
            out[cid] = (3, doc_id)
    broad2 = [t for t in rubric.get("broad2", []) if t]
    if broad2 and len(out) <= MAX_GRADE3:
        b2 = enumerate_tokens(conn, broad2)
        if 0 < len(b2) <= 20:
            for cid, (doc_id, _) in b2.items():
                out.setdefault(cid, (2, doc_id))
    return out


def tier_docs(conn):
    corpus = b.load_corpus(conn)
    dev, hold = b.make_splits(corpus)
    return dev, hold


def build_split(conn, name: str, split_docs: dict, ocr_docs: set, target: int = 60):
    df = b.token_df([d for ds in split_docs.values() for d in ds])
    items, rejected = [], []
    used_q = set()
    per_doc = Counter()
    tq = TIER_QUOTA[name]
    fq = FAMILY_QUOTA[name]
    # 槽位：家族×分层轮转，tier 配额优先
    tiers = [t for t in tq if split_docs.get(t)]
    slots = []
    remain_t = dict(tq)
    ti = 0
    for fam, need in fq.items():
        while need > 0:
            t = tiers[ti % len(tiers)]; ti += 1
            if remain_t[t] <= 0:
                avail = [x for x in tiers if remain_t[x] > 0]
                if not avail:
                    break
                t = avail[0]
            slots.append((t, fam)); remain_t[t] -= 1; need -= 1
    for t in tiers:
        while remain_t[t] > 0:
            slots.append((t, "multi_evidence")); remain_t[t] -= 1

    for tier, fam in slots:
        docs = sorted(split_docs.get(tier, []), key=lambda d: (per_doc[d["id"]], b.h("pilot", d["id"])))
        made = None
        attempts = 0
        for d in docs:
            if attempts >= 12:
                break
            if per_doc[d["id"]] >= 1:
                continue
            got = author(fam, tier, d, df)
            if not got:
                continue
            q, rubric, meta = got
            if q in used_q:
                continue
            attempts += 1
            pos = enumerate_positives(conn, rubric)
            g3 = [c for c, (gr, _) in pos.items() if gr == 3]
            if not g3 or len(g3) > MAX_GRADE3 or len(pos) > MAX_POS:
                rejected.append({"tier": tier, "family": fam, "doc": d["id"],
                                 "reason": f"unsuitable_positives({len(pos)}/{len(g3)})"})
                continue
            made = {"query": q, "family": fam, "corpus_tier": tier, "source_type": b.SOURCE_TYPE[tier],
                    "rubric": rubric, "judging_meta": meta, "doc": d, "gold": pos}
            break
        if not made:
            continue
        doc = made.pop("doc"); pos = made.pop("gold")
        g3 = sorted([c for c, (gr, _) in pos.items() if gr == 3])
        g2 = sorted([c for c, (gr, _) in pos.items() if gr == 2])
        chunks = [{"chunk_id": c, "grade": 3} for c in g3] + [{"chunk_id": c, "grade": 2} for c in g2]
        it = {
            "query": made["query"], "query_type": made["family"], "source_type": made["source_type"],
            "corpus_tier": made["corpus_tier"], "difficulty": "hard" if made["family"] in
            ("mechanism", "multi_evidence", "comparison") else "medium",
            "temporal": made["family"] == "temporal" or bool(made["judging_meta"].get("period")),
            "split": name,
            "gold": {"mode": "chunk_ids", "chunks": chunks},
            "source_hashes": [{"document_id": doc["id"], "sha256": doc["sha256"]}],
            "judging": {"rubric": made["rubric"], "meta": made["judging_meta"],
                        "n_positives": len(pos), "n_grade3": len(g3),
                        "pooled": False, "fn_audit": False},
            "notes": f"claim-specific family={made['family']} tier={made['corpus_tier']} "
                     f"discriminators={made['judging_meta']}",
            "version": "1.0",
        }
        items.append(it)
        used_q.add(it["query"])
        per_doc[doc["id"]] += 1

    # backfill：补足 target（保持 family ≤35%、每文档 ≤1；tier 由余额决定）
    fam_cap = int(target * 0.35)
    fam_count = Counter(i["query_type"] for i in items)
    tier_cap = int(target * 0.35)
    tier_count = Counter(i["corpus_tier"] for i in items)
    attempts = 0
    for tier in sorted(split_docs, key=lambda t: (tier_count[t], t)):
        if len(items) >= target or attempts >= 160:
            break
        for d in sorted(split_docs[tier], key=lambda x: b.h("bf", x["id"])):
            if len(items) >= target or attempts >= 160:
                break
            if per_doc[d["id"]] >= 1 or tier_count[tier] >= tier_cap:
                continue
            for fam in FAMILIES:
                if fam_count[fam] >= fam_cap:
                    continue
                got = author(fam, tier, d, df)
                if not got:
                    continue
                q, rubric, meta = got
                if q in used_q:
                    continue
                attempts += 1
                pos = enumerate_positives(conn, rubric)
                g3 = [c for c, (gr, _) in pos.items() if gr == 3]
                if not g3 or len(g3) > MAX_GRADE3 or len(pos) > MAX_POS:
                    continue
                g3s = sorted(g3)
                g2s = sorted(c for c, (gr, _) in pos.items() if gr == 2)
                items.append({
                    "query": q, "query_type": fam, "source_type": b.SOURCE_TYPE[tier],
                    "corpus_tier": tier,
                    "difficulty": "hard" if fam in ("mechanism", "multi_evidence", "comparison") else "medium",
                    "temporal": fam == "temporal" or bool(meta.get("period")), "split": name,
                    "gold": {"mode": "chunk_ids",
                             "chunks": [{"chunk_id": c, "grade": 3} for c in g3s]
                                       + [{"chunk_id": c, "grade": 2} for c in g2s]},
                    "source_hashes": [{"document_id": d["id"], "sha256": d["sha256"]}],
                    "judging": {"rubric": rubric, "meta": meta, "n_positives": len(pos),
                                "n_grade3": len(g3), "pooled": False, "fn_audit": False},
                    "notes": f"claim-specific family={fam} tier={tier} discriminators={meta}",
                    "version": "1.0"})
                used_q.add(q); per_doc[d["id"]] += 1
                fam_count[fam] += 1; tier_count[tier] += 1
                break
    return items, rejected


def assign_ids(items, prefix):
    out = sorted(items, key=lambda x: (x["corpus_tier"], x["query_type"], x["query"]))
    c = Counter()
    for it in out:
        c[it["query_type"]] += 1
        it["id"] = f"{prefix}-{FAM_SHORT[it['query_type']]}{c[it['query_type']]:02d}"
        it["ocr_derived"] = any(s["document_id"] in b.OCR_DOCS for s in it["source_hashes"])
    return out


FAM_SHORT = {"numeric": "N", "comparison": "C", "mechanism": "M", "temporal": "T",
             "entity_context": "E", "multi_evidence": "X"}


def composition(items):
    tier, fam, st = Counter(), Counter(), Counter()
    docs = set(); ocr = 0; pos = []
    for it in items:
        tier[it["corpus_tier"]] += 1; fam[it["query_type"]] += 1; st[it["source_type"]] += 1
        ocr += 1 if it.get("ocr_derived") else 0
        pos.append(it["judging"]["n_positives"])
        for s in it["source_hashes"]:
            docs.add(s["document_id"])
    n = len(items)
    return {"n": n, "by_tier": dict(sorted(tier.items())), "by_family": dict(sorted(fam.items())),
            "by_source_type": dict(sorted(st.items())), "distinct_gold_docs": len(docs),
            "ocr_derived": ocr, "ocr_share": round(ocr / n, 4) if n else 0,
            "max_tier_share": round(max(tier.values()) / n, 4) if n else 0,
            "min_tier_share": round(min(tier.values()) / n, 4) if n else 0,
            "max_family_share": round(max(fam.values()) / n, 4) if n else 0,
            "positives_median": sorted(pos)[len(pos) // 2] if pos else 0,
            "positives_max": max(pos) if pos else 0}


def write_jsonl(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["development", "holdout", "both"], default="development")
    ap.add_argument("--outdir")
    ap.add_argument("--manifest")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    conn = ro()
    b.OCR_DOCS = {r["id"] for r in conn.execute(
        "SELECT DISTINCT d.id FROM documents d JOIN chunks c ON c.document_id=d.id "
        "WHERE c.plain_text LIKE '%- 发布：%OCR%'")}
    dev, hold = tier_docs(conn)
    if a.report:
        for t in sorted(set(list(dev) + list(hold))):
            print(f"{t:16s} dev={len(dev.get(t,[])):5d} hold={len(hold.get(t,[])):5d}")
        return 0
    results = {}
    for name, sd in (("development", dev), ("holdout", hold)):
        if a.split not in (name, "both"):
            continue
        items, rej = build_split(conn, name, sd, b.OCR_DOCS, TARGETS[name])
        items = assign_ids(items, "DEV" if name == "development" else "HOLD")
        comp = composition(items)
        results[name] = {"items": items, "rejected": rej, "composition": comp}
        print(f"[{name}] n={comp['n']} ocr={comp['ocr_derived']} rejected={len(rej)} "
              f"max_tier={comp['max_tier_share']} max_family={comp['max_family_share']} "
              f"pos_median={comp['positives_median']} pos_max={comp['positives_max']}")
        print("  tier:", json.dumps(comp["by_tier"], ensure_ascii=False))
        print("  family:", json.dumps(comp["by_family"], ensure_ascii=False))
    if a.outdir:
        for name, r in results.items():
            p = Path(a.outdir) / f"{name}_pilot_v1.jsonl"
            write_jsonl(p, r["items"]); print("wrote", p)
    if a.manifest:
        man = {"benchmark": "p8-bench-02-pilot", "version": "1.0", "seed": SEED,
               "generator": "docs/p8_review/scripts/p8_bench_pilot_build.py",
               "catalog": str(CATALOG), "legacy_targets_excluded": sorted(LEGACY_TARGETS),
               "tier_quota": TIER_QUOTA, "family_quota": FAMILY_QUOTA, "splits": {}}
        for name, r in results.items():
            raw = json.dumps(r["items"], ensure_ascii=False, sort_keys=True).encode("utf-8")
            man["splits"][name] = {"n": len(r["items"]), "sha256": hashlib.sha256(raw).hexdigest(),
                                   "composition": r["composition"],
                                   "rejected_count": len(r["rejected"]), "rejected": r["rejected"]}
        Path(a.manifest).write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote manifest", a.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
