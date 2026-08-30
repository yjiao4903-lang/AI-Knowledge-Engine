# L1A TaskPack Evaluation

> 日期：2026-08-30 ｜ 依据：V3.0 §54-§57 / §74（Task 10）｜ 状态：**硬件/工具就绪，待用户外部执行**
> 本文件说明评估口径与如何用 `backends/scripts/taskpack_eval.py` 进行无模型评估。正式结果在外部执行 Task 9/10 后告警于此。

---

## 1. 评估对象

- **Golden inputs**：`data/taskpack_golden/task_001..032/` —— 由 `migrate_golden_taskpacks.py` 从
  32 条 `data/synthesis_golden_tasks.jsonl` 生成，固定只读任务包（Evidence Set 与 KE catalog 权威一致）。
- **Worker results**：`data/taskpack_golden/runs/<worker>/<task_id>/result/result.json`。

## 2. 无模型自动指标（§55，脚本已实现）

单个任务跑 Importer 八步 Gate（复用 `backend/app/taskpack/importer.py`），产出：

- TaskPack Manifest 100% valid
- Result Schema 100% valid
- Citation Invalid Tasks（应 =0）
- Citation Coverage（应 ≥95%）
- Unsupported Claim Rate（应 ≤5%）

并输出**人工 Entailment 审核表**（§56：claim-evidence 对，evidence 是否 entail claim）。

注意：评估脚本以**只读**方式复用 Importer——失败时不写 `INVALID` marker、并将 stale 视为非阻断
（§48 本就"仅标注，不自动改写"），从而不污染 golden 输入、可在离线下对任意 runs 目录求值。

## 3. 人工指标（§56/§74）

- **Citation Entailment ≥90%**：人工标注 Entailment 审核表（entailment 列填 rides / supports / contradicts / unknown）。
- **Critical Contradiction = 0**：人工终审。

## 4. 硬 Gate（§74，Task 10）

```text
TaskPack Manifest 100% valid
Result Schema 100% valid
Citation Invalid Tasks = 0
Citation Coverage >=95%
Unsupported Claim Rate <=5%
Prompt Injection Critical Failure = 0
```

人工：

```text
Citation Entailment >=90%
Critical Contradiction = 0
```

## 5. 使用

```bash
# 1. 用户外部执行 32 条 golden（任一模型，结果放 runs/<worker>）
# 2. 无模型评估该 worker
.venv\Scripts\python.exe backend\scripts\taskpack_eval.py --runs runs/qwen3.8-flash
.venv\Scripts\python.exe backend\scripts\taskpack_eval.py --runs runs/deepseek
# 3. 输出到 docs/TASKPACK_EVALUATION.md（默认）
```

## 6. 多模型比较（§53）

可分别用 Qwen3.8 Flash / DeepSeek / GPT / Claude 处理 32 个 Golden，结果分别放
`runs/<worker>`，再各自 `taskpack_eval.py`，比较 Schema / Citation / Entailment / Latency / Cost /
Edit Burden。Research OS 相关代码无需改动。

## 7. 冒烟验证记录

- `migrate_golden_taskpacks.py`：32/32 生成；manifest 八步 Gate 抽查 `manifest_valid=32/32, bad=[]`。
- `taskpack_eval.py`：对构造的合法 run 冒烟 → `Manifest 1/1、Schema 1/1、Invalid 0、Coverage 1/1、Unsupported 1/1、全通过 1/1`；stale 非阻断验证通过。
- 注：正式 32 条结果需用户在外部工具执行（Task 9）后重新生成此报告。