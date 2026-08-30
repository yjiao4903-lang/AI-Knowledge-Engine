# Cognition Golden Evaluation（I7 P0-4）

> as-of：2026-08-30 ｜ 评测对象：Cognition 只读语义检索（独立 `kb_cognition_chunks_v1` + catalog_cognition.db）
> 标注：人工标注 25 条 query（`data/cognition_golden_queries.jsonl`）｜ 脚本：`backend/scripts/cognition_golden_eval.py`
> 相关：`data/cognition_golden_{queries,results,failures}`

## 覆盖类型（任务书建议覆盖）

| 类型 | 目标 ≥ | 实际 | 说明 |
|---|---|---|---|
| Judgment | ≥5 | 5 | capex 回报判断族 |
| Question | ≥4 | 4 | 变压器前置约束 |
| Topic | ≥4 | 5 | AI 算力/技术革命/就业主题 |
| Project | ≥3 | **0** | 正式认知语料 `06_研究项目` 无任何对象（真实数据缺该类型，无法人工标注） |
| Reading/Review | ≥2 | Reading 5 + Review 2 | 来源阅读 + 复盘 |
| Cross-object | ≥4 | 4 | 跨判断/主题/阅读语义查询 |
| **合计** | ≥20 | **25** | ✅ |

> Project 类型因真实 Cognition 正式语料中暂无 `06_研究项目` 对象而不可标注；其余类型均达建议下限。

## 指标（binary relevance，top10）

| 指标 | 值 | 初始 Gate | 判定 |
|---|---|---|---|
| Hit@1 | **0.760** | — | — |
| Hit@3 | **0.920** | — | — |
| Hit@5 | **1.000** | ≥0.90 | ✅ PASS |
| MRR@10 | **0.853** | ≥0.75 | ✅ PASS |
| NDCG@10 | **0.788** | 仅记录（非硬 blocker） | 记录 |

### 分类型

| 类型 | n | Hit@5 | MRR@10 | NDCG@10 |
|---|---|---|---|---|
| judgment | 5 | 1.000 | 1.000 | 0.718 |
| question | 4 | 1.000 | 0.812 | 0.845 |
| topic | 5 | 1.000 | 0.900 | 0.926 |
| reading | 5 | 1.000 | 0.850 | 0.744 |
| review | 2 | 1.000 | 0.750 | 0.815 |
| cross | 4 | 1.000 | 0.708 | 0.686 |

## 失败（Hit@5 miss）= 0

命中失败 0 条。**结论：Cognition 检索质量满足初始门槛（Hit@5=1.000、MRR=0.853）。**

## 标注口径说明（诚实披露）

- **相关集 = 语义等同的同主题对象**：如 judgment query 的 target 同时含「capex 扩张」编号判断与「capex 增长」主判断（同一判断族多编号，属真实数据冗余）；cross/reading 相关 target 可含主题页与阅读记录。
- **binary relevance + 唯一文档 NDCG**：同一 doc 多 chunk 不重复计入增益（NDCG 已按文档去重归一化，值域 [0,1]）。
- **Project 类型失真**：真实正式认知无 Project 对象，覆盖不足在报告显式标注，不掩盖。

## 与任务书 §7 的呼应

任务书指明「中文短词 FTS 弱项暂不优先修，先用 Cognition Golden 判断 dense/hybrid 是否已满足实际检索」。本组 25 条全部在 **dense/hybrid** 下 Hit@5=1.000，证明当前检索已满足实际认知检索需求，**无需为 Golden 目的重修 Cognition FTS**。lexical 短词弱项（如「就业」0 命中）保留为 known issue，不进本轮优化。