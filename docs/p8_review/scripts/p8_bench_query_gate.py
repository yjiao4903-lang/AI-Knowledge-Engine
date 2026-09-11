# -*- coding: utf-8 -*-
"""P8-BENCH-02：Query Validity Gate（查询自足性预检）与人工作题物化。

背景（Issue #39 · 2026-09-11 WEB-CONTROL 控制决定）
---------------------------------------------------
当前 20 Dev + 10 sealed Holdout 校准包**作废**：领域审阅者指出多条 query 依赖隐藏的源报告
上下文（未定义的"报告中 / 相关指标 / 数量上的差异 / 作用"等），未读过源报告的审阅者无法
可复现地判定相关性。因此新增本 Gate：**只有通过自足性预检的 query 才能进入人审包**。

判定口径（确定性规则，非模型判断）
----------------------------------
一条 query 合格需同时满足：
  1. **无未解析指代**：不得出现 `报告中/文中/该报告/该机构/该公司/上述/本文/前文` 等指代，
     除非指代对象与比较维度已在 query 文本中显式命名；
  2. **显式目标关系**：至少命名 1 个实体（latin 专名，或 `NAMED_ENTITIES` 词表中的中文专名），
     且至少 1 个**具体化维度**（`DIMENSION_TERMS`：营收/毛利率/价格/出货量/产能/capex/概率/
     时间线/机制/份额/目标价/评级/成本/功耗…）；
  3. **无占位式泛化维度**：`相关指标 / 数量上的差异 / 有什么变化 / 起了什么作用 / 怎么样 /
     情况如何 / 有哪些信息` 等一律不合格，除非已具体化；
  4. **成句可问**：含疑问标记，长度 ≥ 8 字符；
  5. **可判候选**：审阅者仅凭 query + 候选块即可给 0/1/2/3（由 1–3 的结构化要求逼近；
     最终由 WEB-CONTROL 对 query 清单的人工 sanity review 兜底）。

> 本 Gate 是**确定性预过滤器**，不是语义裁判。它的作用是把明显不自足的题挡在人审之前；
> 权威判定仍是 WEB-CONTROL 对 Dev query 清单的 sanity review（见 README 流程）。

子命令
------
  check        —— 审计一个题集文件，输出逐题 verdict（JSON + Markdown）
  materialize  —— 把"人工作题 spec"物化为可入池的题集：过 Gate → 校验锚定 → 枚举
                  auto_prelabel 金标 → 分配 id

用法
----
  python docs/p8_review/scripts/p8_bench_query_gate.py check \
      --questions <questions.jsonl> --out <audit.json> --md <audit.md>
  python docs/p8_review/scripts/p8_bench_query_gate.py materialize \
      --authored <authored.jsonl> --split development --out <questions.jsonl> \
      --gate-out <audit.json>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[3]
GATE_VERSION = "1.0"

# 未解析指代 / 指向源报告本身的表述（除非对象与维度已显式命名）
# 注意：`文中` 需排除"论文中"这一良性词内匹配；其余模式均为独立指代表达。
DEICTIC = [
    r"报告中", r"(?<!论)文中", r"(?<!论)文中提到", r"该报告", r"该文", r"本文", r"本报告",
    r"上述", r"前述", r"前文", r"后文", r"该机构", r"该公司", r"该产品", r"该事件",
    r"报告指出", r"报告认为", r"如上所述", r"前面提到", r"据文中",
    r"the report", r"this report", r"the document", r"in the report",
]
# 占位式泛化维度（必须具体化后才能使用）
GENERIC = [
    r"相关指标", r"相关数据", r"相关信息", r"数量上的差异", r"有什么变化", r"有哪些变化",
    r"出现了哪些变化", r"出现了什么变化", r"起什么作用", r"有什么作用", r"作用是什么",
    r"起了什么作用", r"怎么样", r"如何描述", r"情况如何", r"有哪些信息", r"有什么信息",
    r"相关情况", r"有何影响", r"如何看待",
]
# 具体化维度词表（至少命中 1 个）
DIMENSION_TERMS = [
    "营收", "营业收入", "收入", "revenue", "净利润", "营业利润", "利润", "毛利率", "gm",
    "净利率", "利润率", "margin", "eps", "每股收益", "现金流", "fcf", "指引", "guidance",
    "目标价", "评级", "rating", "市占率", "份额", "share", "出货量", "交付量", "销量",
    "装机", "产能", "capex", "资本开支", "订单", "积压订单", "backlog", "库存", "均价",
    "价格", "定价", "pricing", "成本", "cost", "功耗", "power", "时延", "延迟", "带宽",
    "算力", "flops", "tflops", "参数", "良率", "渗透率", "增速", "同比", "环比", "cagr",
    "概率", "时间线", "时间表", "机制", "原因", "驱动", "导致", "下调", "上调", "涨幅",
    "跌幅", "下跌", "上涨", "政策", "裁员", "节省", "回款", "现金消耗", "arr", "规模",
    "估值", "融资", "投资", "持股", "占比", "bit growth", "均价",
    # v1.1 扩充（人工作题实际用到的具体维度）
    "单价", "人数", "疗效", "样本量", "增长", "需求", "受益", "成交量", "短缺", "供应",
    "采购", "波动", "扩容", "倍数", "趋势", "排序", "对比", "差异", "中位", "区间",
    "日均", "全年", "同比增速", "rollout", "deployment", "adoption",
    "患者", "入组", "比例", "视力", "试验",
    "风险", "幅度", "回补", "标的", "占用", "定价权", "折旧", "订单量",
]
# 中文专名词表（Gate 只承认显式列出的名称；可按需扩展并版本化）
NAMED_ENTITIES = [
    "英伟达", "台积电", "中芯国际", "阿里巴巴", "特斯拉", "谷歌", "亚马逊", "微软", "三星",
    "海力士", "博通", "苹果", "meta", "美光", "超微", "华为", "腾讯", "百度", "字节跳动",
    "深度求索", "厄尔尼诺", "标普", "纳斯达克", "美联储", "欧洲央行", "日本央行",
]
QUESTION_MARKS = ("吗", "么", "多少", "几", "哪", "如何", "为什么", "为何", "是否", "多少",
                  "什么", "怎么", "?", "？")

LATIN_ENTITY = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9&.\-]{1,}(?![A-Za-z0-9])")
# 允许的全大写缩写/代码（AVGO / HBM / NOAA / ARR / EBITDA）
ACRONYM = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9&.\-]{1,}(?![A-Za-z0-9])")


def gate_query(query: str) -> dict:
    """返回 {"valid": bool, "violations": [...], "signals": {...}}。"""
    q = (query or "").strip()
    low = q.lower()
    v: list[str] = []

    for pat in DEICTIC:
        if re.search(pat, low):
            v.append(f"未解析指代/指向源报告：{pat}")
    for pat in GENERIC:
        if re.search(pat, q):
            v.append(f"泛化占位维度未具体化：{pat}")

    ents = sorted(set(LATIN_ENTITY.findall(q)) | set(ACRONYM.findall(q))
                  | {e for e in NAMED_ENTITIES if e in low})
    dims = sorted({d for d in DIMENSION_TERMS if d in low})
    has_qmark = any(t in q for t in QUESTION_MARKS)

    if not ents:
        v.append("未命名任何实体（需 latin 专名或词表中的中文专名）")
    if not dims:
        v.append("未命名任何具体化维度（营收/毛利率/价格/产能/capex/概率/机制/份额…）")
    if not has_qmark:
        v.append("缺少疑问标记")
    if len(q) < 8:
        v.append("query 过短")

    return {"valid": not v, "violations": v,
            "signals": {"entities": ents, "dimensions": dims, "length": len(q)}}


# ------------------------------------------------------------------ check
def cmd_check(a) -> int:
    qs = [json.loads(l) for l in Path(a.questions).read_text(encoding="utf-8").splitlines() if l.strip()]
    per, bad = [], []
    for q in qs:
        r = gate_query(q["query"])
        rec = {"id": q.get("id"), "query": q["query"], "corpus_tier": q.get("corpus_tier"),
               "query_type": q.get("query_type"), **r}
        per.append(rec)
        if not r["valid"]:
            bad.append(rec)
    audit = {
        "gate_version": GATE_VERSION, "questions": str(a.questions),
        "n": len(qs), "n_valid": len(qs) - len(bad), "n_invalid": len(bad),
        "pass": not bad,
        "invalid": bad,
        "dimension_coverage": dict(sorted(Counter(
            d for r in per for d in r["signals"]["dimensions"]).items(), key=lambda x: -x[1])[:20]),
        "entity_coverage": sorted({e for r in per for e in r["signals"]["entities"]}),
        "per_query": per,
    }
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.md:
        L = [f"# Query Validity Gate 审计（gate v{GATE_VERSION}）", "",
             f"- 题集：`{a.questions}`", f"- 总数 **{audit['n']}** ｜ 通过 **{audit['n_valid']}**"
             f" ｜ 不通过 **{audit['n_invalid']}**", f"- Gate 结论：**{'PASS' if audit['pass'] else 'FAIL'}**", "",
             "> 本 Gate 是确定性预过滤器，不是语义裁判；权威判定为 WEB-CONTROL 对 Dev query 清单的 sanity review。", "",
             "| id | tier | family | verdict | 违反项 |", "|---|---|---|---|---|"]
        for r in per:
            L.append(f"| `{r['id']}` | {r['corpus_tier']} | {r['query_type']} | "
                     f"{'✅' if r['valid'] else '❌'} | {'；'.join(r['violations']) or '—'} |")
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in audit.items() if k not in ("per_query", "invalid")},
                     ensure_ascii=False, indent=2))
    if bad:
        print("\nINVALID:")
        for r in bad:
            print(f"  {r['id']}: {r['query']}\n     -> {'；'.join(r['violations'])}")
    return 0 if audit["pass"] else 1


# ------------------------------------------------------------------ materialize
def cmd_materialize(a) -> int:
    import p8_bench_build as b
    import p8_bench_pilot_build as pb

    conn = b.ro()
    b.OCR_DOCS = {r["id"] for r in conn.execute(
        "SELECT DISTINCT d.id FROM documents d JOIN chunks c ON c.document_id=d.id "
        "WHERE c.plain_text LIKE '%- 发布：%OCR%'")}
    dev, hold = b.make_splits(b.load_corpus(conn))
    active = dev if a.split == "development" else hold
    allowed_docs = {d["id"]: d for ds in active.values() for d in ds}

    spec = [json.loads(l) for l in Path(a.authored).read_text(encoding="utf-8").splitlines() if l.strip()]
    items, gate_rows, problems = [], [], []
    for i, s in enumerate(spec, 1):
        qid = f"{a.prefix}{i:02d}"
        g = gate_query(s["query"])
        gate_rows.append({"id": qid, "query": s["query"], **g})
        if not g["valid"]:
            problems.append(f"{qid}: Query Validity Gate 不过 —— {'；'.join(g['violations'])}")

        row = conn.execute(
            "SELECT id, document_id, plain_text, heading_path FROM chunks WHERE id=?",
            (s["ground_chunk"],)).fetchone()
        if row is None:
            problems.append(f"{qid}: 锚定 chunk 不存在 {s['ground_chunk']}")
            continue
        if row["document_id"] not in allowed_docs:
            problems.append(f"{qid}: 锚定 chunk 不属于 {a.split} split（反泄漏）")
            continue
        blob = ((row["plain_text"] or "") + "\n" + (row["heading_path"] or "")).lower()
        missing = [t for t in s["req"] if t.lower() not in blob]
        if missing:
            problems.append(f"{qid}: 锚定 chunk 未包含 req token {missing}")
        pats = [re.compile(p, re.I) for p in s.get("requires_any", [])]
        if pats and not all(p.search(blob) for p in pats):
            problems.append(f"{qid}: 锚定 chunk 未满足 requires_any 谓词")

        rubric = {"req": list(s["req"]), "broad2": list(s.get("broad2", [])),
                  "requires_any": list(s.get("requires_any", []))}
        pos = pb.enumerate_positives(conn, rubric)
        g3 = [c for c, (gr, _) in pos.items() if gr == 3]
        if not g3:
            problems.append(f"{qid}: rubric 枚举不到 grade-3 正例（req 过窄）")
        elif len(g3) > pb.MAX_GRADE3 or len(pos) > pb.MAX_POS:
            problems.append(f"{qid}: 正例过多 g3={len(g3)} pos={len(pos)}（req 过宽）")

        doc = allowed_docs[row["document_id"]]
        family = s["family"]
        items.append({
            "query": s["query"], "query_type": family,
            "source_type": b.SOURCE_TYPE[s["tier"]], "corpus_tier": s["tier"],
            "difficulty": s.get("difficulty", "hard" if family in
                                ("mechanism", "multi_evidence", "comparison") else "medium"),
            "temporal": bool(s.get("temporal", family == "temporal")),
            "split": a.split,
            "gold": {"mode": "chunk_ids",
                     "chunks": [{"chunk_id": c, "grade": 3} for c in sorted(g3)]
                               + [{"chunk_id": c, "grade": 2}
                                  for c, (gr, _) in sorted(pos.items()) if gr == 2]},
            "source_hashes": [{"document_id": doc["id"], "sha256": doc["sha256"]}],
            "judging": {"rubric": rubric,
                        "meta": {"authored": True, "ground_chunk": s["ground_chunk"],
                                 "tier": s["tier"], "family": family,
                                 "discriminators": {"entity": s.get("entity"),
                                                    "dimension": s.get("dimension"),
                                                    "period": s.get("period")}},
                        "n_positives": len(pos), "n_grade3": len(g3),
                        "pooled": False, "fn_audit": False,
                        "evidence_class": "authored_query__auto_prelabel_gold"},
            "notes": s.get("notes", ""), "version": "2.0-authored", "id": qid,
            "ocr_derived": doc["id"] in b.OCR_DOCS,
        })

    if problems and not a.allow_problems:
        print(json.dumps({"pass": False, "problems": problems}, ensure_ascii=False, indent=2))
        return 1

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for it in sorted(items, key=lambda x: x["id"]):
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    gate_audit = {"gate_version": GATE_VERSION, "authored": str(a.authored), "split": a.split,
                  "n": len(gate_rows), "n_valid": sum(1 for r in gate_rows if r["valid"]),
                  "pass": all(r["valid"] for r in gate_rows), "per_query": gate_rows}
    if a.gate_out:
        Path(a.gate_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.gate_out).write_text(json.dumps(gate_audit, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    comp = Counter((it["corpus_tier"], it["query_type"]) for it in items)
    print(json.dumps({
        "pass": True, "written": str(out), "n": len(items),
        "gate": {"n": gate_audit["n"], "n_valid": gate_audit["n_valid"], "pass": gate_audit["pass"]},
        "by_tier": dict(sorted(Counter(i["corpus_tier"] for i in items).items())),
        "by_family": dict(sorted(Counter(i["query_type"] for i in items).items())),
        "ocr_derived": sum(1 for i in items if i["ocr_derived"]),
        "positives_median": sorted(i["judging"]["n_positives"] for i in items)[len(items) // 2],
        "tier_family": {f"{k[0]}/{k[1]}": v for k, v in sorted(comp.items())},
        "problems": problems,
    }, ensure_ascii=False, indent=2))
    return 0


# ------------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="P8-BENCH-02 Query Validity Gate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="审计题集的自足性")
    c.add_argument("--questions", required=True)
    c.add_argument("--out")
    c.add_argument("--md")
    c.set_defaults(func=cmd_check)

    m = sub.add_parser("materialize", help="把人工作题 spec 物化为可入池题集")
    m.add_argument("--authored", required=True)
    m.add_argument("--split", required=True, choices=["development", "holdout"])
    m.add_argument("--out", required=True)
    m.add_argument("--gate-out")
    m.add_argument("--prefix", default="DEV2-")
    m.add_argument("--allow-problems", action="store_true")
    m.set_defaults(func=cmd_materialize)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
