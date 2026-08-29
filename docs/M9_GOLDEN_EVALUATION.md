# M9 Golden Evaluation Report（Human-Labeled）

日期：2026-08-29 21:16
语料：10 篇报告 / 725 chunks / 10 docs（索引 43.3s）
Golden Set：50 条人工章节级标注（grade 3/2，data/golden_queries.jsonl）

## Ablation 汇总（Addendum §57）

| Arm | Hit@1 | Hit@3 | Hit@5 | Recall@5 | Recall@10 | MRR@10 | NDCG@10 | P50/P95 ms |
|---|---|---|---|---|---|---|---|---|
| terms | 0.36 | 0.7 | 0.72 | 0.384 | 0.5 | 0.535 | 0.599 | 0.0/0.0 |
| trigram | 0.38 | 0.52 | 0.54 | 0.35 | 0.413 | 0.455 | 0.466 | 0.0/0.0 |
| lexical | 0.44 | 0.76 | 0.78 | 0.434 | 0.517 | 0.599 | 0.652 | 1.3/1.9 |
| dense | 0.68 | 0.88 | 0.94 | 0.518 | 0.612 | 0.773 | 0.779 | 39.0/58.1 |
| hybrid | 0.6 | 0.82 | 0.9 | 0.491 | 0.601 | 0.73 | 0.751 | 41.0/60.9 |
| hybrid_boost | 0.58 | 0.86 | 0.92 | 0.494 | 0.599 | 0.724 | 0.758 | 78.7/104.4 |
| hybrid_rerank | 0.78 | 0.94 | 0.96 | 0.614 | 0.731 | 0.869 | 0.897 | 990.2/1198.6 |

## 分类型 Hit@5 / MRR（Addendum §58）

| 类型 | n | 最优 Arm | Hit@5（各 arm） | MRR（各 arm） |
|---|---|---|---|---|
| causal | 8 | hybrid_boost | {'terms': 0.75, 'trigram': 0.625, 'lexical': 0.75, 'dense': 0.75, 'hybrid': 0.75, 'hybrid_boost': 0.875, 'hybrid_rerank': 0.75} | {'terms': 0.557, 'trigram': 0.5, 'lexical': 0.688, 'dense': 0.75, 'hybrid': 0.771, 'hybrid_boost': 0.775, 'hybrid_rerank': 0.783} |
| comparison | 6 | terms | {'terms': 1.0, 'trigram': 0.5, 'lexical': 1.0, 'dense': 1.0, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} | {'terms': 0.833, 'trigram': 0.5, 'lexical': 0.833, 'dense': 1.0, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} |
| cross_document | 5 | dense | {'terms': 0.4, 'trigram': 0.4, 'lexical': 0.8, 'dense': 1.0, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} | {'terms': 0.4, 'trigram': 0.4, 'lexical': 0.6, 'dense': 0.667, 'hybrid': 0.55, 'hybrid_boost': 0.517, 'hybrid_rerank': 0.64} |
| exact | 6 | trigram | {'terms': 0.833, 'trigram': 1.0, 'lexical': 1.0, 'dense': 0.833, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} | {'terms': 0.854, 'trigram': 0.833, 'lexical': 0.917, 'dense': 0.833, 'hybrid': 0.917, 'hybrid_boost': 0.917, 'hybrid_rerank': 1.0} |
| metric | 5 | terms | {'terms': 1.0, 'trigram': 1.0, 'lexical': 1.0, 'dense': 1.0, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} | {'terms': 0.667, 'trigram': 0.65, 'lexical': 0.8, 'dense': 0.74, 'hybrid': 0.8, 'hybrid_boost': 0.8, 'hybrid_rerank': 0.8} |
| monitoring | 5 | dense | {'terms': 0.6, 'trigram': 0.6, 'lexical': 0.8, 'dense': 1.0, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} | {'terms': 0.301, 'trigram': 0.467, 'lexical': 0.435, 'dense': 0.867, 'hybrid': 0.75, 'hybrid_boost': 0.75, 'hybrid_rerank': 1.0} |
| overview | 4 | dense | {'terms': 0.5, 'trigram': 0.0, 'lexical': 0.5, 'dense': 1.0, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} | {'terms': 0.411, 'trigram': 0.0, 'lexical': 0.411, 'dense': 0.467, 'hybrid': 0.521, 'hybrid_boost': 0.583, 'hybrid_rerank': 0.875} |
| reference | 3 | dense | {'terms': 0.0, 'trigram': 0.333, 'lexical': 0.0, 'dense': 1.0, 'hybrid': 0.0, 'hybrid_boost': 0.0, 'hybrid_rerank': 1.0} | {'terms': 0.0, 'trigram': 0.333, 'lexical': 0.0, 'dense': 0.528, 'hybrid': 0.0, 'hybrid_boost': 0.0, 'hybrid_rerank': 1.0} |
| semantic | 8 | dense | {'terms': 0.875, 'trigram': 0.25, 'lexical': 0.75, 'dense': 1.0, 'hybrid': 1.0, 'hybrid_boost': 1.0, 'hybrid_rerank': 1.0} | {'terms': 0.458, 'trigram': 0.271, 'lexical': 0.393, 'dense': 0.854, 'hybrid': 0.781, 'hybrid_boost': 0.729, 'hybrid_rerank': 0.812} |


## 失败归因（Addendum §64-65）

- 完全通过（全部 arm Hit@5=1）：38/50
- 失败桶分布：{"PARTIAL:dense": 1, "PARTIAL:lexical": 6, "BAD_FUSION": 1, "PARTIAL:dense,lexical,hybrid,hybrid_rerank": 1, "PARTIAL:lexical,hybrid": 3}
- 明细见 data/m9_failures.json（含各路 golden 命中溯源）

## Retrieval Quality Gate（Addendum §62）

| 条件 | 阈值 | 实际 | 判定 |
|---|---|---|---|
| Hit@5 | >= 0.90 | 0.96 | PASS |
| MRR@10 | >= 0.75 | 0.869 | PASS |
| NDCG@10 | >= 0.80 | 0.897 | PASS |
| Exact Hit@5 | >= 0.95 | 1.0 | PASS |
| Semantic Hit@5 | >= 0.85 | 1.0 | PASS |

**最优 Arm：hybrid_rerank**

## Reranker 最终判断（Addendum §61）

- Hybrid vs Hybrid+Reranker：Hit@5 0.9 -> 0.96，
  MRR 0.73 -> 0.869，NDCG 0.751 -> 0.897
- 结论：Reranker 默认 ON
