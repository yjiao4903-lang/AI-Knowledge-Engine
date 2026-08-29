# M6 Hybrid Evaluation Report

日期：2026-08-29 19:25
语料：407 chunks / 5 docs；RRF k=60，weights dense=1.0/terms=0.9/trigram=0.7，parent_boost=1.08

## 汇总（16 条混合类型 Query）

| 模式 | Hit@5 | MRR@10 | 延迟 P50 ms |
|---|---|---|---|

| dense | 15/16 = 0.938 | 0.842 | 41 |
| lexical | 15/16 = 0.938 | 0.844 | 1 |
| hybrid | 16/16 = 1.000 | 0.865 | 75 |

## 每条 Query 明细

| Query | 类型 | truth | Dense Hit@5/MRR | Lexical Hit@5/MRR | Hybrid Hit@5/MRR | Hybrid Top1 |
|---|---|---|---|---|---|---|
| 为什么大型 AI GPU 对先进封装越来越依赖？ | semantic | 36 | 1/1.0 | 1/0.5 | 1/1.0 | M04:ch5-3:o2:0067 |
| 为什么先进光刻反而可能降低大芯片经济性？ | causal | 16 | 1/1.0 | 1/0.333 | 1/0.5 | M04:ch4-2:0057 |
| 玻尔兹曼极限是多少 | metric | 38 | 1/0.5 | 1/1.0 | 1/1.0 | M04:ch1-2:o1:0012 |
| HBM4 的接口位宽是多少 | metric | 5 | 1/1.0 | 1/1.0 | 1/1.0 | M04:ch3-2:o1:0040 |
| CoWoS-L 与 CoWoS-S 有什么区别 | exact | 8 | 1/1.0 | 1/1.0 | 1/1.0 | M04:ch3-1:o1:0037 |
| EXE:5000 的成本和吞吐问题是什么 | exact | 5 | 0/0.143 | 1/1.0 | 1/1.0 | M04:ch2-2:0025 |
| MR-MUF 与 TC-NCF 的差异 | comparison | 8 | 1/1.0 | 1/1.0 | 1/1.0 | M04:ch3-2:o2:0043 |
| AI 是否消除了半导体周期 | causal | 33 | 1/1.0 | 1/1.0 | 1/1.0 | M04:ch5-2:0063 |
| 日本半导体的能力陷阱是什么 | semantic | 7 | 1/0.5 | 1/0.5 | 1/0.5 | M04:ch4-1:0051 |
| 哪些指标监控 CoWoS 紧张 | monitoring | 63 | 1/0.333 | 1/1.0 | 1/0.333 | M04:ch3-1:o1:0037 |
| 液冷为什么成为高密算力基础设施的必然 | semantic | 42 | 1/1.0 | 0/0.167 | 1/0.5 | M04:ch4-2:0057 |
| Transformer 的上下文长度瓶颈在哪里 | semantic | 49 | 1/1.0 | 1/1.0 | 1/1.0 | M09:top1:o2:o4:0002 |
| 数据中心电网并网等待期为什么是硬约束 | causal | 37 | 1/1.0 | 1/1.0 | 1/1.0 | M04:ch5-3:o2:0067 |
| 蛋白质结构预测如何改变药物研发 | semantic | 44 | 1/1.0 | 1/1.0 | 1/1.0 | M18:top1:o22:0028 |
| 资本开支与自由现金流缺口的剪刀差 | metric | 17 | 1/1.0 | 1/1.0 | 1/1.0 | M04:ch5-3:o1:0066 |
| 晶圆代工模式为什么崛起 | semantic | 23 | 1/1.0 | 1/1.0 | 1/1.0 | M04:ch4-2:0055 |


## Gate（Addendum §41）

- Hybrid 不得整体显著差于 Dense 和 Lexical：
  Hit@5 hybrid=1.000 vs dense=0.938 vs lexical=0.938 -> PASS
  MRR hybrid=0.865 vs dense=0.842 vs lexical=0.844 -> PASS
- 每条结果记录 dense_rank/terms_rank/trigram_rank/rrf（Debug Trace 单测覆盖）：PASS
