# P8-BENCH-02 人工判定 vs 自动预标注 · development

- 已判定题数：**20 / 20** ｜ reviewer_kind：['human']
- **human_review_complete**：`True`
- 处置分布：{'accept': 20}
- 进入指标计算的题数：**20** ｜ 排除（reject/ambiguous）：**0**
- **候选级完整度**（accept/rewrite）：fully_graded **20 / 20**（coverage `1.0`）；未完整题：无
- 候选判定覆盖：395 / 395（100.0%）

## auto_prelabel 与人工判定的分歧

| 指标 | 值 |
|---|---|
| candidate 级 grade 完全一致率 | 0.4759 |
| ±1 grade 一致率 | 0.7063 |
| 二值相关（≥2）precision / recall / F1 | 0.8667 / 0.1884 / 0.3095 |
| grade-3 集合 Jaccard（均值） | 0.4605 |
| 人工判为相关但**预标注金标未收录**的块数 | 112 |


## 人审池 recall（benchmark-side，k=20）

| 视图 | 平均 recall |
|---|---|
| dense | 0.5695 |
| hybrid | 0.6481 |
| hybrid_rerank | 0.7199 |
| lexical | 0.4122 |
| union | 0.5695 |

benchmark-side 计算，不改变检索行为；只覆盖人审判定过的候选（有界池）。

## 正式指标

人工 gold 落盘后由既有评测器重算（**不改检索行为**）：

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_trace.py --exp p8_bench02_development_human --questions <development_gold.jsonl> --split development
```

