# p8_trace · F1_w1_1_07

- 时间：2026-09-11T13:18:59
- 题集：E:\研报提取资料库\_golden\benchmark\legacy_v1\golden_queries.jsonl（split=legacy, n=50, unresolved=0）
- filters：`all`
- 语料：documents=3566 chunks=296380

## 1. 逐层 gold 名次（失败题）

| id | type | dense | terms | trigram | union50 | fused | rerank_in | reranked | final | bucket |
|---|---|---|---|---|---|---|---|---|---|---|
| E02 | exact | None | None | 6 | 106 | 76 | None | None | None | FUSION |
| S01 | semantic | 37 | 3 | None | 37 | 7 | 7 | 11 | None | RERANK |
| C01 | causal | 34 | 16 | None | 34 | 33 | None | None | None | FUSION |
| C03 | causal | 20 | None | None | 20 | 41 | None | None | None | FUSION |
| W01 | monitoring | None | None | None | None | None | None | None | None | NO_RECALL |
| O02 | overview | None | 29 | None | 71 | 56 | None | None | None | FUSION |
| R01 | reference | None | None | 16 | 110 | 107 | None | None | None | FUSION |
| X01 | cross_document | 24 | None | None | 24 | 40 | None | None | None | FUSION |
| X03 | cross_document | None | None | None | None | None | None | None | None | NO_RECALL |

## 2. Candidate Recall / Presence

> **Presence = 题级候选存在率**（该题任一 gold>=2 出现在该层）。这是「召回 vs 排序」的决定性分叉。

| 指标 | 值 |
|---|---|
| presence · dense50 | 0.86 |
| presence · terms50 | 0.78 |
| presence · trigram30 | 0.46 |
| presence · union50 | 0.96 |
| presence · fusion30 | 0.84 |
| presence · fusion50 | 0.9 |
| presence · rerank24 | 0.84 |
| presence · final_hit5 | 0.82 |

| 指标 | 值 |
|---|---|
| section-recall · dense@50 | 0.598 |
| section-recall · lexical@50 | 0.462 |
| section-recall · union@50 | 0.598 |
| section-recall · fusion@30 | 0.578 |
| section-recall · fusion@50 | 0.628 |
| section-recall · rerank@10 | 0.526 |

## 3. 7 臂指标（本次复跑）

| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|
| terms | 0.14 | 0.42 | 0.5 | 0.294 | 0.354 | 49.8 | 293.9 |
| trigram | 0.08 | 0.24 | 0.3 | 0.177 | 0.227 | 49.8 | 293.9 |
| lexical | 0.2 | 0.32 | 0.48 | 0.31 | 0.369 | 49.8 | 293.9 |
| dense | 0.44 | 0.54 | 0.64 | 0.518 | 0.546 | 35.6 | 93.4 |
| hybrid | 0.32 | 0.64 | 0.68 | 0.49 | 0.552 | 89.0 | 351.4 |
| hybrid_boost | 0.36 | 0.64 | 0.72 | 0.52 | 0.584 | 89.0 | 351.4 |
| hybrid_rerank | 0.52 | 0.72 | 0.82 | 0.641 | 0.679 | 865.6 | 1273.0 |

## 4. 自校验 vs 已发布回归（±0.02）

**pass = False**

| Arm | Δhit5 | Δmrr | Δndcg | within |
|---|---|---|---|---|
| terms | +0.0 | +0.0 | +0.0 | True |
| trigram | +0.0 | +0.0 | +0.0 | True |
| lexical | +0.0 | +0.0 | -0.001 | True |
| dense | +0.0 | -0.003 | -0.007 | True |
| hybrid | -0.08 | -0.04 | -0.027 | False |
| hybrid_boost | -0.02 | -0.039 | -0.015 | False |
| hybrid_rerank | +0.0 | +0.001 | +0.001 | True |

## 5. 失败归因分布（P8 bucket）

```
{"OK": 41, "FUSION": 6, "RERANK": 1, "NO_RECALL": 2}
```