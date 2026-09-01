# Golden32 R2.3 correction 外部 Worker 启动提示

请在本包根目录从固定 evidence 从零完整重生成 `task_014` 和 `task_030` 两个任务的 result，不得只改单个 claim，不得读取或复用任何旧结果。禁止联网、读取包外资料或修改输入文件。

本轮唯一重点：将直接可验证的融资、资本开支和已观测集中度事实标为 `supported`；将“争夺未来通道霸权”及其他未来目标、阶段情景、预测性后果单独拆出，标为 `inference` 或 `uncertain`。不得把目标/情景、未来预测、估算、TAM、市场份额或无直接证据的强因果混入 `supported`。复核两任务全部 claims 与 tensions，所有对象必须填写合法 `epistemic_state`（supported/inference/uncertain）。

每任务必须完整输出 `result/result.json`、`result/run_meta.json`、`result/DONE`，回传位置固定为 `RETURN/codex-external-golden32-r2-3-correction/task_NNN/result/`。每个 evidence 引用必须来自本任务 `evidence.jsonl`。禁止自动写入 Cognition、Proposal 或正式知识库。完成后回传整个 `RETURN` 文件夹。
