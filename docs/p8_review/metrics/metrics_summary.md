# P8-0 · P7 基线冻结（只读快照）

- 冻结时间：2026-09-11T13:03:52
- 生成脚本：`pipeline/p8_freeze_baseline.py`
- 权威生产配置：`D:/AI-Knowledge-Engine/config/config.yaml`（sha256 `6d3167314db424a0252ec7a9e9534954c06a83b0280d2e16e2211f6bbd5426dd`）
- 回归产物发布时间：2026-09-11T11:12:26

## 1. 语料规模（重要：发布回归与当前存在漂移）

- **发布回归时**（`full_corpus_regression.json`）：documents **3565** / chunks **296341**
- **本快照冻结时**：documents **3566** / sections 62248 / chunks **296385** / qdrant 296385 / consistent=True
- 文档数漂移：**+1**；chunk 数漂移：**+44**
- 漂移原因：P7 收尾后多次 backend 启动 reconcile 重解析了 `M04`/`M09`/`_最终报告`（其中 `_最终报告` 为新增 doc_id）；同批文件的两次重解析得到过不同的 chunk 数（如 M09 45→77），说明**引擎重解析存在非确定性**，已作为 P8 观察项记录。
- **统计口径**：P7 发布回归 JSON 为冻结的**权威历史基线**，本目录不重跑、不覆盖；后续实验以同脚本在**当前**语料复跑并单列。

## 2. 索引构成

- 旗舰归档（`source_path LIKE 'D:\AI%'`）：**187** 篇
- E 盘研报语料：**3379** 篇

## 3. 检索链路参数（生产配置快照）

| 参数 | 值 |
|---|---|
| dense_k | 50 |
| fts_terms_k | 50 |
| fts_trigram_k | 30 |
| fused_k | 30 |
| rerank_k（**死配置，未被引擎使用**） | 24 |
| final_k | 10 |
| reranker.candidate_k（**实际重排截断**） | 24 |
| rrf_k | 60 |
| fusion weights (dense/terms/trigram) | 1.0 / 0.9 / 0.7 |
| parent_boost | 1.08（enabled=True, sections_k=8） |
| embedding | Qwen/Qwen3-Embedding-0.6B @ D:/AI-Models/Qwen3-Embedding-0.6B |
| reranker | Qwen/Qwen3-Reranker-0.6B |

> **层深事实**：`SearchEngine.search` 只用 `fused_k=30` 截断，随后把整段交给 `RerankerService`；后者按 `reranker.candidate_k=24` 再次截断。故**融合名次 25–30 的金标没有任何重排机会**（对应报告 §6.1 的候选深度问题）。

## 4. 各臂指标（发布回归，n=50）

| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) | Hit@5 Wilson 95%CI |
|---|---|---|---|---|---|---|---|---|
| terms | 0.14 | 0.42 | 0.5 | 0.294 | 0.354 | 0.0 | 0.0 | [0.3664, 0.6336] |
| trigram | 0.08 | 0.24 | 0.3 | 0.177 | 0.227 | 0.0 | 0.0 | [0.191, 0.4375] |
| lexical | 0.2 | 0.32 | 0.48 | 0.31 | 0.37 | 42.7 | 319.8 | [0.348, 0.6149] |
| dense | 0.44 | 0.54 | 0.64 | 0.521 | 0.553 | 39.1 | 62.9 | [0.5014, 0.7586] |
| hybrid | 0.38 | 0.66 | 0.76 | 0.53 | 0.579 | 84.5 | 391.7 | [0.6259, 0.857] |
| hybrid_boost | 0.42 | 0.68 | 0.74 | 0.559 | 0.599 | 128.2 | 382.7 | [0.6045, 0.8413] |
| hybrid_rerank | 0.52 | 0.72 | 0.82 | 0.64 | 0.678 | 1014.9 | 1410.7 | [0.692, 0.9023] |

## 5. Gate 判定（发布）

| 指标 | 实测 | 门线 | 判定 | Wilson 95%CI |
|---|---|---|---|---|
| hybrid_rerank Hit@5 | 0.82 | 0.9 | **FAIL** | [0.692, 0.9023] (n=50) |
| MRR | 0.64 | 0.75 | **FAIL** |  |
| NDCG | 0.678 | 0.8 | **FAIL** |  |
| exact Hit@5 | 0.833 | 0.95 | **FAIL** | [0.4365, 0.9699] (n=6) |
| semantic Hit@5 | 0.875 | 0.85 | **PASS** | [0.5291, 0.9776] (n=8) |

**gate_pass = False**

## 6. 失败构成（发布）

- 失败题数：9 / 50
- 分型：{"BAD_FUSION": 1, "BEST_ARM_FAIL": 1, "LOW_DENSE_RANK": 5, "NO_RECALL": 2}
- 明细见 `full_corpus_regression_failures.json`

## 7. 只读与禁止覆盖

本目录为 P8-0 基线冻结快照，**禁止覆盖**。任何实验产物写 `_golden/p8_experiments/`。