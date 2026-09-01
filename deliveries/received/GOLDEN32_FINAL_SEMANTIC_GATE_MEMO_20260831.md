# Golden32 最终语义 Gate 汇总备忘

日期：2026-08-31

## 结论

最终映射后的 Golden32 可判定为：

- **R2 政策语义 Gate：PASS**。已审计的未来/预测/估算/目标/情景、强因果和 `epistemic_state` 边界问题均在对应替换版本中完成修正。
- **全量人工 Citation Entailment Gate：CONDITIONAL / NEEDS-HUMAN**。当前证据能证明引用可定位、重点高风险对象已定向审查，但没有一份独立、可复核的全 32 任务 claim-evidence 人工标注表，因此不能宣称全量 entailment 已达到 `>=90%`。
- **正式导入：不自动放行**。建议进入正式导入前的人工审批阶段；审批对象仍保持 source/candidate，不得自动写入 Cognition 或 Proposal。

## 最终版本映射

| 任务集合 | 采用版本 | 范围 | 语义结论 |
|---|---|---|---|
| R2.1 基线 | R2.1 semantic 回包 | 除 `task_004/014/022/030` 外的 28 项 | 通过既有 R2.1 定向审计 |
| R2.2 替换 | R2.2 correction semantic 回包 | `task_004`、`task_022` | inference/uncertain 边界已修正 |
| R2.3 替换 | R2.3 correction semantic 回包 | `task_014`、`task_030` | 未来目标/情景已从 supported 拆出 |

## 对象统计

按最终映射对各版本实际 `result.json` 聚合：

- 总对象：344
- claims：293
- tensions：51
- `supported`：173
- `inference`：87
- `uncertain`：84
- 缺失/非法 `epistemic_state`：0（最终映射涉及的所有对象）

统计不是 32 个任务数，而是所有最终采用结果中的 claim/tension 对象数；同一任务不重复计入。

## 已审计的高风险范围

高风险复核覆盖了以下类别：未来年份（含 `2026E/2027E`）、预测/估算、TAM/市场份额/渗透率、目标/情景、`必然/不可逆/导致/驱动` 等强因果或强确定性措辞，以及 `[L1 因果证实]` 归因标签。

重点对象及替换结果：

- R2.1 原问题对象：`task_001/claim_004`、`task_004/claim_007`、`task_008/claim_007`、`task_013/claim_006`、`task_014/claim_007-008`、`task_024/claim_005`、`task_025/claim_002`、`task_030/claim_006`、`task_031/claim_003-004`。
- R2.2 修正后采用：`task_004`、`task_022`；过度训练“必然演化”已转为带 `Q≫D` 前提的 `inference`。
- R2.3 修正后采用：`task_014`、`task_030`；融资/资本开支事实保留 `supported`，而“争夺未来通道霸权”、可能过剩和不可逆价值迁移分别拆为 `inference/uncertain`。
- R2.3 的两个任务中，市场份额估算保留“约/可达/第三方研究估算”限定并标 `uncertain`；所有 tensions 均有合法状态。

## 证据与剩余风险

已完成的层面：

- 三轮回包均以各自 delivery 内固定 `evidence.jsonl` 为证据源；最终替换结果的引用均可定位到对应 evidence。
- R2.2 覆盖 4 个任务、39 个对象；R2.3 覆盖 2 个任务、25 个对象；最终 R2.1 基线取 28 个任务、307 个对象。
- 三轮审计均未观察到与固定 evidence 明确相反的主张；当前 `Critical Contradiction = 0`。

仍未完成或不应掩盖的层面：

1. 没有全量 344 个对象的一对一人工 `supports/contradicts/unknown` 标注表，故全局 Citation Entailment 百分比仍是未量化项。
2. 机器 citation coverage/引用格式通过，不等于证据蕴含通过；尤其报告自身的 `[L1]` 标签不能单独构成直接因果证据。
3. 最终 32 项的正式导入仍需独立确认 `run_meta`、prompt hash、DONE、membership、stale 和结果版本映射；本 memo 不替代 Task10 机器 Gate。
4. 任何进入人工审批的对象都应保留 provenance、来源口径和 epistemic state，禁止因语义 Gate PASS 自动晋升为正式 Cognition/Proposal。

## 建议

允许将最终映射作为“正式导入前人工审批”候选集，但不允许自动导入或宣称 L1A/Task10 full pass。人工审批至少应：

- 对全部高风险对象和全部 tensions 做 claim-evidence 标注；
- 从四类 task type 分层抽查普通 claims，直到能够独立计算 Citation Entailment；
- 只有在 entailment `>=90%`、Critical Contradiction `=0`、无 R2 硬规则违例且机器 Gate 全绿后，才可讨论正式导入。

## 审计材料路径

- R2.1：`deliveries/received/semantic-golden32-r2-1-final/`
- R2.2：`deliveries/received/semantic-r2-2-final/`
- R2.3：`deliveries/received/semantic-r2-3-final/`
- R2.3 固定要求：`deliveries/external-codex-taskpack-golden32-r2-3-correction-20260831/REMEDIATION_NOTES.md`
