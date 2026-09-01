# Golden32 R2.1 外部 Worker 启动提示

这是 Golden32 R2.1 correction run。请在本包根目录工作，一次重新处理 `task_001` 至 `task_032` 全部任务。必须从每个任务包内的固定 `evidence.jsonl` 从零生成结果，绝不读取、复制或参考任何旧 R1/R2 结果。

硬约束：

1. 只依据本包内该任务的 `evidence.jsonl`、`task.yaml`、`output_schema.json` 和说明文件；禁止联网、禁止读取包外资料、禁止修改任何输入文件。
2. 每个任务都必须输出 `result/result.json`、`result/run_meta.json` 和 `result/DONE`。输出位置固定为 `RETURN/codex-external-golden32-r2-1/task_NNN/result/`。
3. 所有 claims 与 tensions 都必须填写 `epistemic_state`，且只能是 `supported`、`inference`、`uncertain`。不得留空。
4. 2026E/2027E 及其他未来年份、预测、估算、TAM、市场份额、渗透率、目标、情景和规划口径不得标为 `supported`；须保留原始限定词并标为 `uncertain` 或 `inference`。
5. 没有直接证据的因果关系不得标为 `supported`，不得使用“必然”“不可逆”“导致”之类超出证据的强因果；拆为直接支持的事实与明确标注的 inference。
6. 对 `task_001/claim_004`、`task_004/claim_007`、`task_008/claim_007`、`task_013/claim_006`、`task_014/claim_007`、`task_014/claim_008`、`task_024/claim_005`、`task_025/claim_002`、`task_030/claim_006`、`task_031/claim_003`、`task_031/claim_004` 做重点纠正，并复核所有其他高风险对象。
7. 不得把任何结果自动写入正式 Cognition、Proposal、知识库或其他生产数据。

完成后只需把整个 `RETURN` 文件夹带回用户，不要手工合并文件。若分批处理，32 个 task 必须全部完成后再写最终 DONE/反馈；反馈中列出每个 task 的状态和缺失项。
