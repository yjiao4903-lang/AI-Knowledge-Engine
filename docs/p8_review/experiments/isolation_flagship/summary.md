# p8_trace · isolation_flagship

- 时间：2026-09-11T13:15:38
- 题集：E:\研报提取资料库\_golden\benchmark\legacy_v1\golden_queries.jsonl（split=legacy, n=50, unresolved=0）
- filters：`flagship`（allowed_chunks=9675）
- 语料：documents=3566 chunks=296380

## 1. 逐层 gold 名次（失败题）

| id | type | dense | terms | trigram | union50 | fused | rerank_in | reranked | final | bucket |
|---|---|---|---|---|---|---|---|---|---|---|
| E02 | exact | None | None | 2 | 101 | 49 | None | None | None | FUSION |
| C01 | causal | 28 | 11 | None | 28 | 39 | None | None | None | FUSION |
| C03 | causal | 12 | None | None | 12 | 24 | 24 | 8 | 8 | RERANK |
| R01 | reference | 12 | None | 16 | 12 | 10 | 10 | 7 | 7 | RERANK |
| X01 | cross_document | 19 | None | None | 19 | 31 | None | None | None | FUSION |

## 2. Candidate Recall / Presence

> **Presence = 题级候选存在率**（该题任一 gold>=2 出现在该层）。这是「召回 vs 排序」的决定性分叉。

| 指标 | 值 |
|---|---|
| presence · dense50 | 0.96 |
| presence · terms50 | 0.82 |
| presence · trigram30 | 0.54 |
| presence · union50 | 1.0 |
| presence · fusion30 | 0.94 |
| presence · fusion50 | 1.0 |
| presence · rerank24 | 0.94 |
| presence · final_hit5 | 0.9 |

| 指标 | 值 |
|---|---|
| section-recall · dense@50 | 0.689 |
| section-recall · lexical@50 | 0.498 |
| section-recall · union@50 | 0.689 |
| section-recall · fusion@30 | 0.675 |
| section-recall · fusion@50 | 0.732 |
| section-recall · rerank@10 | 0.621 |

## 3. 7 臂指标（本次复跑）

| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|
| terms | 0.2 | 0.46 | 0.58 | 0.354 | 0.406 | 71.9 | 468.8 |
| trigram | 0.22 | 0.4 | 0.44 | 0.318 | 0.351 | 71.9 | 468.8 |
| lexical | 0.3 | 0.4 | 0.58 | 0.403 | 0.456 | 71.9 | 468.8 |
| dense | 0.52 | 0.64 | 0.76 | 0.605 | 0.628 | 124.4 | 156.0 |
| hybrid | 0.44 | 0.68 | 0.8 | 0.578 | 0.633 | 196.5 | 613.0 |
| hybrid_boost | 0.42 | 0.72 | 0.78 | 0.578 | 0.633 | 196.5 | 613.0 |
| hybrid_rerank | 0.62 | 0.86 | 0.9 | 0.752 | 0.789 | 926.6 | 1307.2 |

## 4. 自校验 vs 已发布回归（±0.02）

**pass = False**

| Arm | Δhit5 | Δmrr | Δndcg | within |
|---|---|---|---|---|
| terms | +0.08 | +0.06 | +0.052 | False |
| trigram | +0.14 | +0.141 | +0.124 | False |
| lexical | +0.1 | +0.093 | +0.086 | False |
| dense | +0.12 | +0.084 | +0.075 | False |
| hybrid | +0.04 | +0.048 | +0.054 | False |
| hybrid_boost | +0.04 | +0.019 | +0.034 | False |
| hybrid_rerank | +0.08 | +0.112 | +0.111 | False |

## 5. 失败归因分布（P8 bucket）

```
{"OK": 45, "FUSION": 3, "RERANK": 2}
```