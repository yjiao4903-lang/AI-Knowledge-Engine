# p8_trace · A2_fused50_rerank40

- 时间：2026-09-11T13:12:25
- 题集：E:\研报提取资料库\_golden\benchmark\legacy_v1\golden_queries.jsonl（split=legacy, n=50, unresolved=0）
- filters：`all`
- 语料：documents=3566 chunks=296380

## 1. 逐层 gold 名次（失败题）

| id | type | dense | terms | trigram | union50 | fused | rerank_in | reranked | final | bucket |
|---|---|---|---|---|---|---|---|---|---|---|
| E02 | exact | None | None | 6 | 106 | 65 | None | None | None | FUSION |
| S06 | semantic | 8 | 23 | None | 8 | 8 | 8 | 6 | 6 | RERANK |
| C01 | causal | 34 | 16 | None | 34 | 40 | 40 | 9 | 9 | RERANK |
| C03 | causal | 20 | None | None | 20 | 33 | 33 | 13 | None | RERANK |
| P02 | comparison | None | 1 | 15 | 51 | 9 | 9 | 6 | 6 | RERANK |
| W01 | monitoring | None | None | None | None | None | None | None | None | NO_RECALL |
| O02 | overview | None | 29 | None | 71 | 62 | None | None | None | FUSION |
| R01 | reference | None | None | 16 | 110 | 97 | None | None | None | FUSION |
| X01 | cross_document | 24 | None | None | 24 | 36 | 36 | 8 | 8 | RERANK |
| X03 | cross_document | None | None | None | None | None | None | None | None | NO_RECALL |

## 2. Candidate Recall / Presence

> **Presence = 题级候选存在率**（该题任一 gold>=2 出现在该层）。这是「召回 vs 排序」的决定性分叉。

| 指标 | 值 |
|---|---|
| presence · dense50 | 0.86 |
| presence · terms50 | 0.78 |
| presence · trigram30 | 0.46 |
| presence · union50 | 0.96 |
| presence · fusion30 | 0.9 |
| presence · fusion50 | 0.9 |
| presence · rerank24 | 0.9 |
| presence · final_hit5 | 0.8 |

| 指标 | 值 |
|---|---|
| section-recall · dense@50 | 0.598 |
| section-recall · lexical@50 | 0.462 |
| section-recall · union@50 | 0.598 |
| section-recall · fusion@30 | 0.583 |
| section-recall · fusion@50 | 0.63 |
| section-recall · rerank@10 | 0.56 |

## 3. 7 臂指标（本次复跑）

| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|
| terms | 0.14 | 0.42 | 0.5 | 0.294 | 0.354 | 49.0 | 354.7 |
| trigram | 0.08 | 0.24 | 0.3 | 0.177 | 0.227 | 49.0 | 354.7 |
| lexical | 0.2 | 0.32 | 0.48 | 0.31 | 0.37 | 49.0 | 354.7 |
| dense | 0.44 | 0.54 | 0.64 | 0.518 | 0.546 | 34.4 | 63.6 |
| hybrid | 0.36 | 0.64 | 0.74 | 0.513 | 0.567 | 91.2 | 413.3 |
| hybrid_boost | 0.4 | 0.66 | 0.72 | 0.542 | 0.587 | 91.2 | 413.3 |
| hybrid_rerank | 0.52 | 0.7 | 0.8 | 0.642 | 0.695 | 1410.7 | 1896.7 |

## 4. 自校验 vs 已发布回归（±0.02）

**pass = True**

| Arm | Δhit5 | Δmrr | Δndcg | within |
|---|---|---|---|---|
| terms | +0.0 | +0.0 | +0.0 | True |
| trigram | +0.0 | +0.0 | +0.0 | True |
| lexical | +0.0 | +0.0 | +0.0 | True |
| dense | +0.0 | -0.003 | -0.007 | True |
| hybrid | -0.02 | -0.017 | -0.012 | True |
| hybrid_boost | -0.02 | -0.017 | -0.012 | True |
| hybrid_rerank | -0.02 | +0.002 | +0.017 | True |

## 5. 失败归因分布（P8 bucket）

```
{"OK": 40, "FUSION": 3, "RERANK": 5, "NO_RECALL": 2}
```