# M7 Evaluation Report

日期：2026-08-29 19:53
设备：worker cuda:1（rocm）；Mini Human Eval：16 条查询（人工章节级 grade 3/2 标注，data/m7_human_eval.jsonl）

## A/B 汇总（Addendum §24-25）

| 指标 | Hybrid | Hybrid + Reranker |
|---|---|---|
| Hit@1 | 0.625 | **0.750** |
| Hit@3 | 0.812 | **0.938** |
| Hit@5 | 0.938 | **0.938** |
| MRR@10 | 0.740 | **0.842** |
| NDCG@10 | 0.719 | **0.845** |
| 延迟 P50 (ms) | 85.5 | 1084.0（rerank 992.6ms） |
| 延迟 P95 (ms) | 1608.3 | 2387.8（rerank 2289.5ms） |

## 每条 Query 对比（grade>=2 记为相关）

| ID | 类型 | Hybrid Hit@5/MRR | +Reranker Hit@5/MRR | NDCG 变化 |
|---|---|---|---|---|

| Q01 HBM4 的接口位宽是多少？ | metric | 1/1.00 | 1/1.00 | +0.035 |
| Q02 玻尔兹曼极限是多少？ | metric | 1/1.00 | 1/1.00 | +0.097 |
| Q03 CoWoS-L 与 CoWoS-S 有什么区别？ | comparison | 1/1.00 | 1/1.00 | +0.000 |
| Q04 High-NA 为什么导致视场减半？ | causal | 1/1.00 | 1/1.00 | +0.125 |
| Q05 EXE:5000 的成本和吞吐问题是什么？ | exact | 1/1.00 | 1/1.00 | +0.166 |
| Q06 先进制程的供电电压为什么很难继续下降？ | causal | 0/0.00 | 0/0.14 | +0.333 |
| Q07 AI 是否消除了半导体周期？ | causal | 1/1.00 | 1/1.00 | +0.087 |
| Q08 日本半导体的能力陷阱是什么？ | semantic | 1/1.00 | 1/1.00 | +0.000 |
| Q09 哪些指标可以监控 CoWoS 产能紧张？ | monitoring | 1/0.25 | 1/1.00 | +0.481 |
| Q10 Transformer 自注意力的计算复杂度瓶颈 | metric | 1/0.50 | 1/1.00 | +0.112 |
| Q11 状态空间模型（SSM/Mamba）为什么被认为能 | semantic | 1/0.50 | 1/0.50 | +0.020 |
| Q12 AI 数据中心为什么受电网并网排队制约？ | causal | 1/0.33 | 1/0.50 | +0.226 |
| Q13 央行资产负债表扩张与债务危机是什么关系？ | semantic | 1/0.25 | 1/0.33 | +0.032 |
| Q14 蛋白质结构预测如何突破莱文塔尔悖论？ | semantic | 1/1.00 | 1/1.00 | +0.108 |
| Q15 AI 算力扩张面临哪些物理硬约束？ | cross_document | 1/1.00 | 1/1.00 | +0.105 |
| Q16 台积电 N3E 的晶体管密度是多少？ | exact | 1/1.00 | 1/1.00 | +0.087 |


## Worker（Addendum §10-18）

- 独立 OS 进程（spawn）+ Queue 通信：PASS（m7_worker_smoke.py）
- crash -> watchdog restart：PASS（test_crash 后 restarts=1 且恢复推理）
- timeout guard：PASS（test_sleep 8s / timeout 3s 捕获 WorkerTimeout）
- batch benchmark：1=894ms / 2=545ms / 4=308ms / 8=252ms（24 docs，全 finite）
  -> 选定 batch=8（最大稳定 batch）
- 连续崩溃 2 次 -> CPU fallback：实现于 manager._handle_crash

## Gate（Addendum §25）

- Hit@5 不下降：0.938 >= 0.938 -> PASS
- MRR 不明显下降：0.842 >= 0.690 -> PASS
- NDCG 提升：0.719 -> 0.845
- No GPU backend crash（崩溃只杀 worker）：PASS
- 性能目标 P50<=1.5s / P95<=3s：1084.0ms / 2387.8ms -> PASS
