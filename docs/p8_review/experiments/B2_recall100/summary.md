# p8_trace · B2_recall100

- 时间：2026-09-11T13:17:49
- 题集：E:\研报提取资料库\_golden\benchmark\legacy_v1\golden_queries.jsonl（split=legacy, n=50, unresolved=0）
- filters：`all`
- 语料：documents=3566 chunks=296380

## 1. 逐层 gold 名次（失败题）

| id | type | dense | terms | trigram | union50 | fused | rerank_in | reranked | final | bucket |
|---|---|---|---|---|---|---|---|---|---|---|
| E02 | exact | None | None | 6 | 204 | 66 | None | None | None | FUSION |
| S01 | semantic | 37 | 3 | None | 37 | 7 | 7 | 15 | None | RERANK |
| S06 | semantic | 8 | 23 | None | 8 | 9 | 9 | 6 | 6 | RERANK |
| C01 | causal | 34 | 16 | None | 34 | 45 | None | None | None | RERANK_DEPTH |
| C03 | causal | 20 | None | None | 20 | 38 | 38 | 13 | None | RERANK |
| P02 | comparison | None | 1 | 15 | 101 | 11 | 11 | 7 | 7 | RERANK |
| W01 | monitoring | None | 79 | None | 173 | 195 | None | None | None | FUSION |
| R01 | reference | None | None | 16 | 210 | 100 | None | None | None | FUSION |
| X01 | cross_document | 24 | None | None | 24 | 44 | None | None | None | RERANK_DEPTH |
| X03 | cross_document | 72 | 53 | None | 72 | 117 | None | None | None | FUSION |

## 2. Candidate Recall / Presence

> **Presence = 题级候选存在率**（该题任一 gold>=2 出现在该层）。这是「召回 vs 排序」的决定性分叉。

| 指标 | 值 |
|---|---|
| presence · dense50 | 0.9 |
| presence · terms50 | 0.82 |
| presence · trigram30 | 0.46 |
| presence · union50 | 1.0 |
| presence · fusion30 | 0.92 |
| presence · fusion50 | 0.92 |
| presence · rerank24 | 0.88 |
| presence · final_hit5 | 0.8 |

| 指标 | 值 |
|---|---|
| section-recall · dense@50 | 0.598 |
| section-recall · lexical@50 | 0.462 |
| section-recall · union@50 | 0.598 |
| section-recall · fusion@30 | 0.585 |
| section-recall · fusion@50 | 0.647 |
| section-recall · rerank@10 | 0.557 |

## 3. 7 臂指标（本次复跑）

| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|
| terms | 0.14 | 0.42 | 0.5 | 0.294 | 0.354 | 47.1 | 314.6 |
| trigram | 0.08 | 0.24 | 0.3 | 0.177 | 0.227 | 47.1 | 314.6 |
| lexical | 0.2 | 0.3 | 0.48 | 0.307 | 0.367 | 47.1 | 314.6 |
| dense | 0.44 | 0.54 | 0.64 | 0.518 | 0.546 | 35.6 | 62.4 |
| hybrid | 0.36 | 0.6 | 0.72 | 0.501 | 0.554 | 86.0 | 354.2 |
| hybrid_boost | 0.4 | 0.62 | 0.72 | 0.533 | 0.586 | 86.0 | 354.2 |
| hybrid_rerank | 0.54 | 0.74 | 0.8 | 0.655 | 0.694 | 1413.6 | 1908.5 |

## 4. 自校验 vs 已发布回归（±0.02）

**pass = False**

| Arm | Δhit5 | Δmrr | Δndcg | within |
|---|---|---|---|---|
| terms | +0.0 | +0.0 | +0.0 | True |
| trigram | +0.0 | +0.0 | +0.0 | True |
| lexical | +0.0 | -0.003 | -0.003 | True |
| dense | +0.0 | -0.003 | -0.007 | True |
| hybrid | -0.04 | -0.029 | -0.025 | False |
| hybrid_boost | -0.02 | -0.026 | -0.013 | False |
| hybrid_rerank | -0.02 | +0.015 | +0.016 | True |

## 5. 失败归因分布（P8 bucket）

```
{"OK": 40, "FUSION": 4, "RERANK": 4, "RERANK_DEPTH": 2}
```