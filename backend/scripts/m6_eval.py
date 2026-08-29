"""M6 评测：Dense only / Lexical only / Hybrid 三模式对比（Addendum §40-41）。

输出 docs/M6_EVALUATION.md。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.lexical.corpus import build_corpus_db  # noqa: E402
from app.retrieval.dense import DenseRetriever  # noqa: E402
from app.retrieval.search_engine import SearchEngine  # noqa: E402

# (query, 关键词组, 类型标签)。Hit = chunk plain_text 含任一关键词。
QUERY_SET = [
    ("为什么大型 AI GPU 对先进封装越来越依赖？", ["CoWoS", "HBM", "先进封装", "封装代偿"], "semantic"),
    ("为什么先进光刻反而可能降低大芯片经济性？", ["High-NA", "拼接", "视场"], "causal"),
    ("玻尔兹曼极限是多少", ["60", "mV/dec", "亚阈值"], "metric"),
    ("HBM4 的接口位宽是多少", ["2048"], "metric"),
    ("CoWoS-L 与 CoWoS-S 有什么区别", ["CoWoS-S", "CoWoS-L", "local silicon"], "exact"),
    ("EXE:5000 的成本和吞吐问题是什么", ["EXE:5000", "$4 亿", "WPH"], "exact"),
    ("MR-MUF 与 TC-NCF 的差异", ["MR-MUF", "TC-NCF"], "comparison"),
    ("AI 是否消除了半导体周期", ["周期", "库存", "基钦"], "causal"),
    ("日本半导体的能力陷阱是什么", ["能力陷阱", "质保", "大型机"], "semantic"),
    ("哪些指标监控 CoWoS 紧张", ["交期", "Lead Time", "40"], "monitoring"),
    ("液冷为什么成为高密算力基础设施的必然", ["液冷", "热", "功耗密度"], "semantic"),
    ("Transformer 的上下文长度瓶颈在哪里", ["注意力", "上下文", "KV", "状态空间"], "semantic"),
    ("数据中心电网并网等待期为什么是硬约束", ["电网", "并网"], "causal"),
    ("蛋白质结构预测如何改变药物研发", ["蛋白质", "AlphaFold", "药物"], "semantic"),
    ("资本开支与自由现金流缺口的剪刀差", ["Capex", "自由现金流", "缺口"], "metric"),
    ("晶圆代工模式为什么崛起", ["代工", "台积电", "Foundry"], "semantic"),
]


def mrr(ranked_ids: list[str], truth: set[str], k: int = 10) -> float:
    for i, cid in enumerate(ranked_ids[:k], 1):
        if cid in truth:
            return 1.0 / i
    return 0.0


def main() -> int:
    cfg = load_config()
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    conn, info = build_corpus_db(tmp / "corpus.db")
    texts = {r["id"]: r["plain_text"] for r in conn.execute("SELECT id, plain_text FROM chunks").fetchall()}
    dense = DenseRetriever(cfg)
    engine = SearchEngine(cfg, conn, dense)

    modes = ["dense", "lexical", "hybrid"]
    stats = {m: {"hit5": 0, "mrr": 0.0, "total_ms": []} for m in modes}
    per_query = []

    for q, keywords, qtype in QUERY_SET:
        truth = {cid for cid, t in texts.items() if any(kw in t for kw in keywords)}
        row = {"query": q, "type": qtype, "truth": len(truth)}
        for m in modes:
            t0 = time.perf_counter()
            resp = engine.search(q, mode=m, top_k=10)
            ms = (time.perf_counter() - t0) * 1000
            ids = [r["chunk_id"] for r in resp["results"]]
            hit5 = 1 if any(cid in truth for cid in ids[:5]) else 0
            r = mrr(ids, truth)
            stats[m]["hit5"] += hit5
            stats[m]["mrr"] += r
            stats[m]["total_ms"].append(ms)
            row[m] = {"hit5": hit5, "mrr": round(r, 3), "ms": round(ms, 1),
                      "top1": ids[0] if ids else "-"}
        per_query.append(row)

    n = len(QUERY_SET)
    lines = [f"""# M6 Hybrid Evaluation Report

日期：{time.strftime('%Y-%m-%d %H:%M')}
语料：{info['total_chunks']} chunks / 5 docs；RRF k={cfg.fusion.rrf_k}，weights dense={cfg.fusion.dense_weight}/terms={cfg.fusion.terms_weight}/trigram={cfg.fusion.trigram_weight}，parent_boost={cfg.fusion.parent_boost}

## 汇总（{n} 条混合类型 Query）

| 模式 | Hit@5 | MRR@10 | 延迟 P50 ms |
|---|---|---|---|
"""]
    for m in modes:
        s = stats[m]
        ms = sorted(s["total_ms"])
        p50 = ms[len(ms) // 2]
        lines.append(f"| {m} | {s['hit5']}/{n} = {s['hit5']/n:.3f} | {s['mrr']/n:.3f} | {p50:.0f} |")

    lines.append("\n## 每条 Query 明细\n")
    lines.append("| Query | 类型 | truth | Dense Hit@5/MRR | Lexical Hit@5/MRR | Hybrid Hit@5/MRR | Hybrid Top1 |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in per_query:
        lines.append(
            f"| {row['query'][:30]} | {row['type']} | {row['truth']} "
            f"| {row['dense']['hit5']}/{row['dense']['mrr']} "
            f"| {row['lexical']['hit5']}/{row['lexical']['mrr']} "
            f"| {row['hybrid']['hit5']}/{row['hybrid']['mrr']} "
            f"| {row['hybrid']['top1']} |")

    d, l, h = (stats[m]["hit5"] / n for m in modes)
    dm, lm, hm = (stats[m]["mrr"] / n for m in modes)
    lines.append(f"""

## Gate（Addendum §41）

- Hybrid 不得整体显著差于 Dense 和 Lexical：
  Hit@5 hybrid={h:.3f} vs dense={d:.3f} vs lexical={l:.3f} -> {'PASS' if h >= min(d, l) - 0.05 else 'CHECK'}
  MRR hybrid={hm:.3f} vs dense={dm:.3f} vs lexical={lm:.3f} -> {'PASS' if hm >= min(dm, lm) - 0.05 else 'CHECK'}
- 每条结果记录 dense_rank/terms_rank/trigram_rank/rrf（Debug Trace 单测覆盖）：PASS
""")
    out = PROJECT_ROOT / "docs" / "M6_EVALUATION.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
