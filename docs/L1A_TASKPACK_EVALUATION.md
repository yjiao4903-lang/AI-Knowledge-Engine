# L1A TaskPack Evaluation

> 日期：2026-08-30 ｜ 依据：V3.0 §54-§57 / §74（Task 10）｜ 状态：**准备中；Task 9/10 尚未完成**
> 本文件说明评估口径与如何用 `backends/scripts/taskpack_eval.py` 进行无模型评估。正式结果在外部执行 Task 9/10 后告警于此。

---

## 1. 评估对象

### R1 / R2 解释

R1 的 4-task smoke 即使机器 Gate 4/4 通过，也只表示协议、Schema、引用和导入链路通过；若预测/估算/未来年份或无直接因果证据的强因果被标为 `supported`，状态仍为“机器通过、语义需修订”。正典 Prompt 修订后，R2 才是重跑候选：必须用新模板重新生成/复制任务包、重新运行外部 Worker，并保留新 prompt SHA 与结果审计，不能把旧结果直接升级为 R2。

- **Golden inputs（已核实存在，32 个）**：`data/taskpack_golden/task_001..032/` —— 由 `migrate_golden_taskpacks.py` 从
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

## 7. 冒烟验证记录（历史/计划性，不计入当前 Task 9/10）

- 曾有构造合法 run 的单任务冒烟记录，但不是 Task 9/10 结果。
- 当前已核实 32 个 Golden 输入包、`backend/scripts/migrate_golden_taskpacks.py` 和 `backend/scripts/taskpack_eval.py` 均存在；`data/taskpack_golden/runs/` 存在但为空，尚无外部 Worker 结果，因此 Task 9/10 为 `blocked`。
- 正式 32 条结果需外部 Worker 执行（Task 9）后，主负责人运行无模型评估并补充真实报告；在此之前不得写“32/32 PASS”。
