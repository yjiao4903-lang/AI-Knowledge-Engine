# p8_trace · F2_w09_1_08

- 时间：2026-09-11T13:20:09
- 题集：E:\研报提取资料库\_golden\benchmark\legacy_v1\golden_queries.jsonl（split=legacy, n=50, unresolved=0）
- filters：`all`
- 语料：documents=3566 chunks=296380

## 1. 逐层 gold 名次（失败题）

| id | type | dense | terms | trigram | union50 | fused | rerank_in | reranked | final | bucket |
|---|---|---|---|---|---|---|---|---|---|---|
| E02 | exact | None | None | 6 | 106 | 45 | None | None | None | FUSION |
| C01 | causal | 34 | 16 | None | 34 | 31 | None | None | None | FUSION |
| C03 | causal | 20 | None | None | 20 | 61 | None | None | None | FUSION |
| W01 | monitoring | None | None | None | None | None | None | None | None | NO_RECALL |
| O02 | overview | None | 29 | None | 71 | 51 | None | None | None | FUSION |
| R01 | reference | None | None | 16 | 110 | 74 | None | None | None | FUSION |
| X01 | cross_document | 24 | None | None | 24 | 49 | None | None | None | FUSION |
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
| presence · final_hit5 | 0.84 |

| 指标 | 值 |
|---|---|
| section-recall · dense@50 | 0.598 |
| section-recall · lexical@50 | 0.462 |
| section-recall · union@50 | 0.598 |
| section-recall · fusion@30 | 0.569 |
| section-recall · fusion@50 | 0.629 |
| section-recall · rerank@10 | 0.514 |

## 3. 7 臂指标（本次复跑）

| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|
| terms | 0.14 | 0.42 | 0.5 | 0.294 | 0.354 | 47.7 | 313.0 |
| trigram | 0.08 | 0.24 | 0.3 | 0.177 | 0.227 | 47.7 | 313.0 |
| lexical | 0.2 | 0.32 | 0.48 | 0.31 | 0.37 | 47.7 | 313.0 |
| dense | 0.44 | 0.54 | 0.64 | 0.518 | 0.546 | 36.8 | 80.8 |
| hybrid | 0.3 | 0.64 | 0.66 | 0.472 | 0.536 | 88.0 | 361.9 |
| hybrid_boost | 0.34 | 0.6 | 0.7 | 0.508 | 0.57 | 88.0 | 361.9 |
| hybrid_rerank | 0.52 | 0.74 | 0.84 | 0.647 | 0.688 | 892.9 | 1229.4 |

## 4. 自校验 vs 已发布回归（±0.02）

**pass = False**

| Arm | Δhit5 | Δmrr | Δndcg | within |
|---|---|---|---|---|
| terms | +0.0 | +0.0 | +0.0 | True |
| trigram | +0.0 | +0.0 | +0.0 | True |
| lexical | +0.0 | +0.0 | +0.0 | True |
| dense | +0.0 | -0.003 | -0.007 | True |
| hybrid | -0.1 | -0.058 | -0.043 | False |
| hybrid_boost | -0.04 | -0.051 | -0.029 | False |
| hybrid_rerank | +0.02 | +0.007 | +0.01 | True |

## 5. 失败归因分布（P8 bucket）

```
{"OK": 42, "FUSION": 6, "NO_RECALL": 2}
```