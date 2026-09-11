# Sealed Holdout 10 calibration — aggregate evidence（v2 批次）

> **状态（2026-09-12，LOCAL-DEV-A）**：sealed Holdout 10 人工判定已完成、导入并冻结。
> `human_review_complete = true`，candidate completeness = 1.0（199/199）。
> 本目录**只含聚合证据**；逐题题目/判定/key/trace 全部留在仓库外密封工作区。

## 权威来源与流程

- 密封工作区：`E:\研报提取资料库\_golden\p8_bench02_adjudication\v2\holdout_calibration_v2\`（仓库外）。
- 包 SHA256 `ddd819968ea5a23c…`，与 key、题集、判定、gold、freeze 的哈希链见
  `holdout_aggregate_v2.json` 的 `hashes_sealed_side`。
- 人工确认：WEB-CONTROL Issue #39 评论 `2026-09-11T17:36:00Z` —— 人工审阅者对
  HOLD2-01…HOLD2-10 全部 10 题"exactly as the proposed blinded recommendations"逐字确认。
  LOCAL-DEV-A 据此把确认的 grades 逐字序列化进密封工作区（`reviewer_kind=human`，
  不做任何改写；provenance 记录存于密封目录）。

## 结果摘要

| 项 | 值 |
|---|---|
| judged | 10/10（accept 10，reject/ambiguous 0） |
| candidate coverage | 1.0（199/199） |
| `human_review_complete` | true |
| FN corrections after human audit | 0 |
| grade≥2 positives/query 分布 | 1×8、2×1、3×1 |
| judged pool size 分布 | 20×9、19×1 |

生产 arm（hybrid_rerank，检索行为零改动）人工 gold 聚合指标：

- Hit@1 **0.600**（Wilson95 [0.313, 0.832]）
- Hit@3 **0.800**（Wilson95 [0.490, 0.943]）
- Hit@5 **1.000**（Wilson95 [0.722, 1.000]）
- MRR **0.728**，NDCG **0.749**
- Recall@20：最终排序深度冻结为 final_k=10，不支持 Recall@20；候选级替代口径
  rerank@10 = 1.0、fusion@50 = 1.0。
- 10/10 buckets OK；p50 1896.6 ms / p95 4323.8 ms。

验证：`p8_bench_adjudicate.py self-test` 32/32 PASS；`p8_bench_verify.py` 全部通过
（Legacy 50 逐字节不变 `aa0412a2…`；Dev∩Holdout 目标文档重合 0；Holdout 不在仓库内）。

## 必须一并披露的限制

1. **确认方式**：人工审阅者是对"proposed blinded recommendations"（来自盲化 key 的
   `auto_prelabel` 提案，二值 0/3 rubric）做整体逐字确认，因此人工 grade 分布不含
   1/2 档，聚合指标与预标注 gold 指标相同。本校准验证的是管线/完整度/密封流程与
   门的通过性，**不是**独立人类相关性研究。
2. n=10，Wilson 区间很宽；池为 4 视图 top-N 有界抽样（标准 pooling 假设）。
3. 本结果是 pilot 验收门证据，不授权 150+150 扩展、检索调参或任何路由/架构决策。
