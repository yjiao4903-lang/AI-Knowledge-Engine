# Golden32 R2.2 correction 外部 Worker 启动提示

请在本包根目录从零处理 `task_004`、`task_014`、`task_022`、`task_030` 四个任务，并为每个任务重新生成完整 `result/result.json`，不得只补改单个 claim。唯一证据来源是各任务包内的 `evidence.jsonl`；禁止联网、读取包外资料、复用任何 R1/R2/R2.1 结果或修改输入文件。

硬要求：

1. 所有 claims 和 tensions 必须填写合法 `epistemic_state`：`supported`、`inference` 或 `uncertain`，不得留空。
2. `task_004/claim_006` 和 `task_022/claim_005` 中“过度训练必然演化”必须拆为直接证据支持的事实与有条件的 `inference/uncertain`，不得标 `supported`。
3. `task_014/claim_003-004`、`task_030/claim_002-003` 中“必然引发暗光纤/暗算力过剩”“不可逆漂移”必须拆分：融资/资本开支/当前集中度等直接事实可标 supported；未来后果、强因果和价值迁移只能标 inference/uncertain，并写明条件、来源口径与不确定性；禁止 L1 direct causal。
4. 未来年份、预测、估算、目标、情景、TAM、市场份额、渗透率和规划口径不得标 `supported`；保留限定词。
5. 没有直接证据的因果关系不得使用强因果事实表述。每个引用必须来自本任务固定 evidence。
6. 每个任务必须输出 `result/result.json`、`result/run_meta.json`、`result/DONE`。

输出固定为：`RETURN/codex-external-golden32-r2-2-correction/task_NNN/result/`。不得自动写入 Cognition、Proposal、正式知识库或其他生产数据。完成后将整个 `RETURN` 文件夹回传用户。
