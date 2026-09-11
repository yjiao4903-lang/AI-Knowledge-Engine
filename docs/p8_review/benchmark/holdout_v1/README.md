# Holdout Benchmark v1（结构与规范；题集待出）

**用途**（规范 §5.2）：最终验收。**调参阶段不得查看逐题结果**（只允许在 Stage 8 一次性评测）。

**规模建议**：50–100 题（规范）。

**split 值**：`holdout`

## 与 Development 的隔离要求

- 题集文件只由验收流程读取；实验脚本在 `--split development` 下**不得**加载 holdout 文件。
- 出题人与调参人分离（至少：holdout 题在 P8 参数实验期间不进入任何 per-query 分析）。
- 题型覆盖与 Development 相同（见 `../development_v1/README.md`），但**不得与 Development 题重复实体/结论**。

## 金标锚定

同 Development：必须 `gold.chunks`（chunk_id 锚定），`unresolved = 0`。禁止 `heading_contains`。

## 校验

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe pipeline\p8_bench_validate.py ^
  --questions _golden\benchmark\holdout_v1\questions_v1.jsonl --split holdout
```

校验规则与 Development 相同（见 `pipeline/p8_bench_validate.py`）。
