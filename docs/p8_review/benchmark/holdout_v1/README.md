# Holdout Benchmark v1（结构与规范；题集待出）

> **2026-09-11 P8-BENCH-02 证据分级更正（WEB-CONTROL / PR #41）**：已生成 40 题 sealed Holdout
> （本地密封，仓库外），并完成机械预标注与 FN 审计；其 gold 属 **`auto_prelabel`**，
> **不是人工相关性判定**。因此"24/40 题池内无 grade-3"只能说明自动 rubric 与检索池不相交，
> **不能**作为 Holdout 效度或检索质量结论。该 40 题**未作为正式 sealed Holdout 发布**；
> 仓库仅保留其 SHA256/组成/聚合指标于 `../pilot_manifest_v1.json`。
> 人工校准包（10 题）已密封生成于仓库外，判定与冻结流程见 `../adjudication/README.md`。
> 当前人工校准门线**未完成**。详见 `../reports/P8_BENCH02_STATUS_20260911.md`。

> **2026-09-11 P8-BENCH-01 状态**：**尚未建立正式 sealed Holdout 题集**。P8-BENCH-01 的
> 机器自动出题方法经基线评测判定金标不可辩护（见 `../reports/P8_BENCH01_STATUS_20260911.md`），
> 因此按 Issue #36 的止损条款不发布 150 题 Holdout，以免以低质量金标充当验收门线。
> Holdout 应使用**人工领域出题**并与 Development 出题人分离；题目/金标只存本地密封路径，
> 仓库仅落 SHA256 freeze manifest 与组成统计（`../benchmark_manifest_v1.json` 框架已就绪）。

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
