# R2.1 修正说明

R2 回包的主要问题是 36 个 tension 缺少 `epistemic_state`，以及部分未来/估算/预测和强因果对象误标为 `supported`。本包要求 32 个任务全部从固定 evidence 重做，不复用历史结果。

重点对象：`task_001/claim_004`、`task_004/claim_007`、`task_008/claim_007`、`task_013/claim_006`、`task_014/claim_007-008`、`task_024/claim_005`、`task_025/claim_002`、`task_030/claim_006`、`task_031/claim_003-004`。

最小验收条件：所有 claims/tensions 的 epistemic_state 非空且合法；未来/预测/估算/目标/情景不得 supported；无直接因果证据不得强因果 supported；每个引用必须来自本任务固定 evidence。回包还需重新执行 schema、manifest、membership、coverage、stale、run_meta 和 DONE 检查。
