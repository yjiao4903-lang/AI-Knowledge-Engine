# M4 Evaluation Report

日期：2026-08-29 19:01
语料：5 篇真实报告 fixture（M04 半导体 / M06 能源基础设施 / M09 AI 模型 / M14 宏观 / M18 生物医疗）

## 索引一致性（Addendum §16）

| 指标 | 值 |
|---|---|
| chunks | 407 |
| chunks_fts_terms | 407 |
| chunks_fts_trigram | 407 |
| 一致 | PASS |

## lexical_text 示例

```
CoWoS-L HBM4 EXE:5000 台积 电 时代 价值量 提升 , 单台 $ 4 亿 。
```

## Exact Identifier Queries（Addendum §17，ground truth = plain_text 包含词项）

| Query | truth chunks | Hit@5 | latency ms | mode |
|---|---|---|---|---|
| CoWoS-L | 7 | True | 0.26 | terms |
| CoWoS-S | 3 | True | 0.21 | terms |
| High-NA | 13 | True | 0.14 | terms |
| EXE:5000 | 3 | True | 0.11 | terms |
| HBM4 | 10 | True | 0.59 | combined |
| HBM4E | 1 | True | 0.18 | combined |
| MR-MUF | 8 | True | 0.1 | terms |
| TC-NCF | 6 | True | 0.09 | terms |
| N3E | 3 | True | 0.47 | combined |
| N3B | 3 | True | 0.17 | combined |
| A16 | 6 | True | 0.22 | combined |
| CFET | 4 | True | 0.29 | combined |
| BSPDN | 4 | True | 0.48 | combined |
| 60mV/dec | 3 | True | 0.11 | terms |
| 429mm² | 1 | True | 0.22 | combined |

**Exact Hit@5 = 1.000（要求 >= 0.95）**

## Chinese Queries（Addendum §18）

| Query | truth chunks | Hit@5 | latency ms | mode |
|---|---|---|---|---|
| 先进封装 | 11 | True | 0.76 | combined |
| 铜互连 | 0 | None | 0.0 | skipped(no-truth) |
| 散热良率 | 1 | True | 0.27 | combined |
| 混合键合 | 7 | True | 0.31 | combined |
| 先进制程 | 13 | True | 0.58 | combined |
| 资本开支 | 12 | True | 0.45 | combined |
| 推理算力 | 0 | None | 0.0 | skipped(no-truth) |
| 电网瓶颈 | 0 | None | 0.0 | skipped(no-truth) |
| 半导体周期 | 2 | True | 0.37 | combined |
| 蛋白质结构 | 1 | True | 0.6 | combined |
| 先进封装与混合键合 | 0 | None | 0.0 | skipped(no-truth) |
| 晶圆代工模式的崛起 | 0 | None | 0.0 | skipped(no-truth) |

**Chinese Hit@5 = 1.000（7/7，要求基本可用）**

## 延迟（ms）

| 模式 | P50 | P95 |
|---|---|---|
| Terms | 0.14 | 0.26 |
| Trigram | 0.21 | 0.49 |
| Combined | 0.37 | 0.76 |

## Gate（Addendum §20/75）

- No FTS syntax errors: PASS（特殊字符 - : / + . _ 全覆盖）
- No index inconsistency: PASS
- Exact Hit@5 >= 0.95: PASS
- Chinese Query 基本正确: PASS
