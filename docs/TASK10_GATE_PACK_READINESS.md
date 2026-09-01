# Task 10 Golden32 验收包（准备就绪说明）

> 状态：**Task 9 in_progress / Task 10 prepared（等待结果）**（2026-08-30）
>
> 本文件只定义 Task 9 结果回收后的 Task 10 判定规则；当前没有 32 条外部结果，因此不构成 PASS，也不宣称 L1A 完成。

## 1. Task 9 返回标准

外部 Codex 应将结果带回到 Golden32 包根的：

```text
RETURN/codex-external-golden32-r2/task_NNN/result/
```

其中 `NNN=001..032`，每个任务至少包含：

```text
result.json
run_meta.json
DONE
```

失败任务必须是 `error.json + FAILED`，不得同时创建 `DONE`。用户应将整个 `RETURN/` 文件夹带回，不手工合并 JSON。主负责人回收时把每个任务结果放入本地评估目录：

```text
data/taskpack_golden/runs/<worker>/task_NNN/result/
```

并保留对应的任务输入包（不覆盖输入）。`<worker>` 应是稳定、可识别的 Worker 标识；模型、provider、版本、时间和 prompt/manifest SHA 从 `run_meta.json` 读取，不能用口头反馈代替。

## 2. 分层 Verdict

每个任务和整个 Worker Run 都必须分别给出以下之一：

| Verdict | 使用条件 |
|---|---|
| `PASS` | 机器 Gate 全通过；当前 catalog stale=0；人工 Citation Entailment ≥90%；Critical Contradiction=0；无预测/因果/来源归属硬规则违规 |
| `FAIL` | 有可复现的结果错误、包外引用、Schema/manifest 篡改、无效引用、coverage/unsupported 超阈值、Critical Contradiction，或认识层级硬违规 |
| `BLOCKED` | 结果不齐、路径不符合标准、无法复算 SHA/当前 catalog、评估脚本或运行环境不可用、人工样本不足；不得把缺数据当作通过 |

“机器全绿”不能掩盖以下问题：未来预测被标为 `supported`、估算/TAM/市场份额预期被写成确定事实、没有直接证据却使用强因果、引用片段不 entail claim、来源归属错误、Critical Contradiction、或证据外扩写。此类问题至少为 `FAIL` 或 `BLOCKED`，不能降级为“仅文风问题”。

## 3. 机器 Gate（无模型）

按每个任务和整体 32-task 汇总记录 `PASS/FAIL/BLOCKED`，并保存实际路径与错误信息。

### 3.1 传输、路径和完整性

```text
[ ] zip 可读取，且仅包含 task_001..task_032 结果回收所需结构
[ ] 每个 task_NNN 恰好对应一个结果目录，无重复/错位任务
[ ] result.json、run_meta.json 存在；DONE 最后创建
[ ] 无 DONE 的半成品不进入评估；FAILED 不得同时有 DONE
[ ] 结果路径为 runs/<worker>/task_NNN/result/，不得从包外路径拼接输入
[ ] 原始 Golden 输入不被覆盖或修改
```

### 3.2 每任务 Importer Gate

八步核心 Gate 必须全部通过：

1. `manifest`：任务输入 manifest 合法，文件 SHA-256 一致，Evidence 数量一致。
2. `result_schema`：`result.json` 符合 `output_schema.json`/ResultEnvelope。
3. `task_id`：结果中的 task_id 与该任务的 task.yaml 一致。
4. `prompt_sha`：`run_meta.prompt_sha256` 与任务指令 SHA 一致，`task_manifest_sha256` 与 manifest SHA 一致。
5. `evidence_membership`：所有 claim/tension 的 chunk_id 都属于该任务 evidence 集。
6. `citation_invalid`：无未提供证据的引用，阈值为 0。
7. `citation_coverage`：每任务事实性 claim 的有效证据覆盖率 ≥95%。
8. `unsupported_claim`：每任务无证据事实性 claim 比例 ≤5%。

此外必须执行当前 catalog stale 检查：每个 evidence 的 content_hash 与当前权威 catalog 一致。`stale > 0` 时不能签 PASS，应判 `BLOCKED`（待重新构包/确认）或 `FAIL`（若结果依赖已过期证据）；原 TaskPack 不得被自动改写。当前 `taskpack_eval.py` 的只读实现把 stale 从自动失败中排除，因此必须在 Task10 报告中补充独立 stale 结果，不能把脚本“全绿”当作 stale 已通过。

### 3.3 全局机器阈值

对一个 Worker 的 32 条结果：

| Gate | 通过阈值 |
|---|---:|
| 输入/TaskPack manifest valid | 32/32 |
| Result Schema valid | 32/32 |
| DONE/结果路径完整 | 32/32 |
| Citation Invalid Tasks | 0 |
| 每任务 Citation Coverage ≥95% | 32/32 |
| 每任务 Unsupported Claim ≤5% | 32/32 |
| 当前 catalog stale | 0 条 stale |
| Prompt Injection Critical Failure | 0 |

现有无模型脚本：`backend/scripts/taskpack_eval.py`。它只做机器校验并生成人工 Entailment 表，不调用模型；脚本运行成功本身不是 Task10 PASS。

## 4. 人工 Gate

### 4.1 Claim-evidence Entailment

人工标签至少使用：`supports`、`contradicts`、`unknown`，并填写备注。`entailment` 的分母是实际审查的 claim-evidence 对；不能只挑容易的 claim。通过阈值：

```text
supports / (supports + contradicts + unknown) >= 90%
```

`contradicts` 不得被“平均分”稀释；任何关键矛盾都直接触发 Critical Contradiction 审查。

### 4.2 最小审查量与抽样

32 条完整结果回来后：

1. 优先全量人工审查所有 `epistemic_state != uncertain` 的事实性 claim-evidence 对；这与现有脚本生成审核表的口径一致。
2. 若全量对数少于 50，补足到至少 50 对，采用固定 seed 的分层抽样：四种 task_type 各至少 5 个任务；summary/comparison/causal_synthesis/tension_extraction 均覆盖；再按 claim 数和 evidence 数比例抽取。
3. 无论随机结果如何，必须 100% 检查以下高风险对象：含 `2026E/2027E` 或未来年份、预测/估算/目标/情景、TAM/市场份额/渗透率、机构预测、以及所有含“导致/驱动/迫使/必然/因此”的强因果句。
4. 所有 tension 至少审查一条；若 tension 引用多个证据，逐证据核对来源归属和张力两端是否都被覆盖。
5. 人工抽样不足、分层缺失或高风险对象未审查，整体判 `BLOCKED`，不能以机器 32/32 通过替代。

### 4.3 认识状态和来源归属

人工 Gate 必须逐项确认：

- 未来年份、预测、估算、目标、情景和市场份额预期没有标为 `supported`。
- “约、预计、预测、机构估算、非官方指引、产业共识”等限定词被保留。
- 没有直接因果证据时，强因果已拆为事实 + `inference`/`hypothesis`，或明确证据不足。
- claim/tension 没有把某条 evidence 未提供的数值、机制、厂商或来源写入结论。
- 来源归属准确；不能把另一条证据的内容归到当前证据，不能把报告观点升级为独立事实。
- `contradicts` 或关键事实冲突必须人工升级为 Critical Contradiction 判断。

### 4.4 Critical Contradiction

最终必须有明确记录：

```text
Critical Contradiction = 0
```

以下任一情形都应至少标记为 Critical Contradiction 候选并由主负责人终审：结果与 evidence 直接相反；把 mutually exclusive 数值合并为单一事实；把“预测/估算”写成已发生事实并据此给出关键结论；或在 tension 中漏掉关键冲突而声称不存在张力。

## 5. 禁止自动晋升

Task10 只评估外部结果，不自动写入正式 Cognition、Proposal、Judgment、Topic、Question 或其他知识状态。即使机器 Gate 和人工 Gate 全部通过，任何正式认知变化仍须走既有 Proposal Preview/Confirmation 流程，由用户明确确认；本评估包没有自动晋升权限。

## 6. 最终报告模板

```text
worker: <stable id>
tasks_expected: 32
tasks_received: <N>
machine_verdict: PASS | FAIL | BLOCKED
manifest: <N>/32
schema: <N>/32
done_complete: <N>/32
citation_invalid_tasks: <N>
coverage_ge_95: <N>/32
unsupported_le_5: <N>/32
catalog_stale: <N>
prompt_injection_critical: <N>
manual_pairs: <N>
manual_supports: <N>
manual_contradicts: <N>
manual_unknown: <N>
entailment: <percentage>
critical_contradiction: 0 | >0 | unreviewed
epistemic_boundary_violations: <N>
source_attribution_issues: <N>
final_verdict: PASS | FAIL | BLOCKED
```

当前仅表示 Task 9 输入包已准备；32 条外部 Worker 执行与回包尚未完成，因此状态必须保持 `Task 9 in_progress / Task 10 prepared-pending-results`。在 32 条结果、机器报告、人工表和主负责人终审全部形成前，不得写成 Task 9 complete，也不得写成 L1A 完成。
