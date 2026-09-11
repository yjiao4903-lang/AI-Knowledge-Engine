# -*- coding: utf-8 -*-
"""P8 旗舰隔离探针对照（只读；读两份 trace.json，产出对照表与结论）。

输入：`_golden/p8_experiments/{A0_baseline_all,isolation_flagship}/trace.json`
输出：
  `_golden/p8_experiments/isolation_flagship/compare.md`  逐题 gold 名次对照
  `p8_analysis/corpus_competition.json`                   量化结论 + 逐题明细
"""
from __future__ import annotations

import json
from pathlib import Path

E = Path(r"E:\研报提取资料库")
EXP = E / "_golden" / "p8_experiments"
ALL = EXP / "A0_baseline_all" / "trace.json"
FLAG = EXP / "isolation_flagship" / "trace.json"
OUT_JSON = E / "p8_analysis" / "corpus_competition.json"
OUT_MD = EXP / "isolation_flagship" / "compare.md"

K = ("dense_rank", "terms_rank", "trigram_rank", "union50_rank", "fused_rank",
     "rerank_input_pos", "final_rank", "bucket")


def rk(v):
    return "-" if v is None else str(v)


def main() -> int:
    a, f = json.loads(ALL.read_text(encoding="utf-8")), json.loads(FLAG.read_text(encoding="utf-8"))
    ta = {t["id"]: t for t in a["traces"]}
    tf = {t["id"]: t for t in f["traces"]}
    ids = [t["id"] for t in a["traces"]]

    def hit5(d):
        return d["summary_by_arm"]["hybrid_rerank"]["hit5"]

    pa, pf = a["candidate_presence"], f["candidate_presence"]
    recovered, residual, unchanged_ok = [], [], []
    rows = []
    for i in ids:
        A, F = ta[i], tf[i]
        fa = A["final_rank"] if A["final_rank"] else 99
        ff = F["final_rank"] if F["final_rank"] else 99
        if fa > 5 and ff <= 5:
            recovered.append(i)
        elif fa > 5 and ff > 5:
            residual.append(i)
        elif fa <= 5 and ff <= 5:
            unchanged_ok.append(i)
        rows.append((i, A, F, fa, ff))

    delta = {
        "hit1": round(f["summary_by_arm"]["hybrid_rerank"]["hit1"] - a["summary_by_arm"]["hybrid_rerank"]["hit1"], 3),
        "hit3": round(f["summary_by_arm"]["hybrid_rerank"]["hit3"] - a["summary_by_arm"]["hybrid_rerank"]["hit3"], 3),
        "hit5": round(hit5(f) - hit5(a), 3),
        "mrr": round(f["summary_by_arm"]["hybrid_rerank"]["mrr"] - a["summary_by_arm"]["hybrid_rerank"]["mrr"], 3),
        "ndcg": round(f["summary_by_arm"]["hybrid_rerank"]["ndcg"] - a["summary_by_arm"]["hybrid_rerank"]["ndcg"], 3),
        "presence_union50": round(pf["union50"] - pa["union50"], 3),
        "presence_fusion30": round(pf["fusion30"] - pa["fusion30"], 3),
        "n_no_recall_all": a["bucket_distribution"].get("NO_RECALL", 0),
        "n_no_recall_flag": f["bucket_distribution"].get("NO_RECALL", 0),
    }
    verdict = {
        "H1_corpus_competition": {
            "claim": "语料竞争压制排序（旗舰隔离后 Hit@5 回升至 ≈0.92）",
            "observed": {"hit5_all": hit5(a), "hit5_flag": hit5(f), "delta": delta["hit5"]},
            "judgement": "成立" if delta["hit5"] >= 0.05 else ("部分成立" if delta["hit5"] > 0 else "不成立"),
            "note": (f"隔离后 Hit@5 回升 {delta['hit5']:+.3f}，NO_RECALL {delta['n_no_recall_all']}→{delta['n_no_recall_flag']}，"
                     f"union50 题级存在率 {pa['union50']}→{pf['union50']}。竞争是主要退化来源，但隔离集内仍有 "
                     f"{len(residual)} 题失败（融合/重排残余），非纯竞争问题。"),
        },
        "residual_failures_in_isolation": residual,
        "recovered_by_isolation": recovered,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(
        {"generated_at": a["generated_at"], "exp_all": "A0_baseline_all", "exp_isolation": "isolation_flagship",
         "metrics_all": a["summary_by_arm"]["hybrid_rerank"], "metrics_isolation": f["summary_by_arm"]["hybrid_rerank"],
         "presence_all": pa, "presence_isolation": pf, "delta": delta, "verdict": verdict,
         "per_query": [{"id": i, "type": ta[i]["type"],
                        "all": {k: ta[i][k] for k in K}, "flagship": {k: tf[i][k] for k in K},
                        "final_delta": (tf[i]["final_rank"] or 99) - (ta[i]["final_rank"] or 99)}
                       for i in ids]}, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# 旗舰隔离探针 · 逐题对照", "",
         "同一批 50 题，同一金标；仅将检索域从**全库 3,566 篇**收窄到**D 盘旗舰归档 187 篇**。",
         "full = /api 全库；flag = 旗舰隔离。“-”表示该层未出现 gold。", "",
         f"- 全库 hybrid_rerank：Hit@5 **{hit5(a)}** / MRR {a['summary_by_arm']['hybrid_rerank']['mrr']} / NDCG {a['summary_by_arm']['hybrid_rerank']['ndcg']}",
         f"- 旗舰 hybrid_rerank：Hit@5 **{hit5(f)}** / MRR {f['summary_by_arm']['hybrid_rerank']['mrr']} / NDCG {f['summary_by_arm']['hybrid_rerank']['ndcg']}",
         f"- ΔHit@5 **{delta['hit5']:+}** ｜ ΔMRR {delta['mrr']:+} ｜ ΔNDCG {delta['ndcg']:+}",
         f"- 题级候选存在率：union50 {pa['union50']} → {pf['union50']}；fusion30 {pa['fusion30']} → {pf['fusion30']}",
         f"- NO_RECALL：{delta['n_no_recall_all']} → {delta['n_no_recall_flag']}",
         "",
         "## 判定",
         "",
         f"**H1（语料竞争压制排序）：{verdict['H1_corpus_competition']['judgement']}**",
         "",
         verdict["H1_corpus_competition"]["note"],
         "",
         f"- 仅靠隔离即恢复前 5：**{recovered or '无'}**",
         f"- 隔离后仍失败：**{residual or '无'}**（属融合/重排/chunk/金标残余）",
         "",
         "## 逐题对照（仅列任一环境失败的题）", "",
         "| id | type | 层 | full | flag |", "|---|---|---|---|---|"]
    for i, A, F, fa, ff in rows:
        if fa <= 5 and ff <= 5:
            continue
        for k in ("dense_rank", "terms_rank", "trigram_rank", "union50_rank", "fused_rank",
                  "rerank_input_pos", "final_rank", "bucket"):
            L.append(f"| {i} | {A['type']} | {k} | {rk(A[k])} | {rk(F[k])} |")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")

    print(json.dumps({"delta": delta, "verdict": verdict["H1_corpus_competition"]["judgement"],
                      "recovered": recovered, "residual": residual}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
