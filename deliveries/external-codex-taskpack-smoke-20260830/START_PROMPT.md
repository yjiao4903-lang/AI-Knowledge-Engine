# 外部 Codex TaskPack Smoke 启动提示词

你正在处理一个外部 Codex Worker 任务包。请在当前包根目录工作，并一次完成以下四个任务：`task_001`、`task_009`、`task_018`、`task_025`。

严格规则：

1. 只读取当前包内四个 `task_NNN/` 目录中的 `task.yaml`、`AGENT_INSTRUCTION.md`、`evidence.jsonl`、`output_schema.json`、`README.md` 和 `manifest.json`。只能依据对应任务的 `evidence.jsonl` 作答；禁止读取包外文件、调用网络或使用外部资料补全。
2. 不得修改任何输入文件（包括 task.yaml、AGENT_INSTRUCTION.md、evidence.jsonl、output_schema.json、README.md、manifest.json）。不得修改或删除 `result/.gitkeep` 以外的输入内容。
3. 每个任务分别生成：`task_NNN/result/result.json`、`task_NNN/result/run_meta.json`，并在这两个文件完成且自检后最后创建 `task_NNN/result/DONE`。禁止写入 CoT；result.json 必须符合该任务的 output_schema.json，evidence_refs 必须逐字复制该任务 evidence.jsonl 中的 chunk_id。
4. `run_meta.json` 必须填写实际 Worker 工具和模型信息，并按任务要求填写 prompt_sha256 与 task_manifest_sha256。无法完成的任务写 `result/error.json` 和 `result/FAILED`，不要创建 DONE。
5. 不要把结果写回正式知识库、Cognition、Proposal 或任何自动知识写入路径；本任务只产生文件结果。

完成后，把四个任务的整个 `result/` 目录复制到包根的 `RETURN/codex-external-smoke/task_NNN/result/`，保留任务编号和文件名；不要覆盖或改动四个原始 `task_NNN/` 目录。若无法复制，请在包根 `RETURN/ERROR.md` 写明原因。

最后回复：四个任务各自的完成/失败状态、实际模型、结果文件相对路径，以及是否已生成 `RETURN/codex-external-smoke/`。不要发送包外路径或输入正文。
