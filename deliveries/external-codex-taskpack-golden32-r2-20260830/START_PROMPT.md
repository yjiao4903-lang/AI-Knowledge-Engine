# Task 9：外部 Codex Golden32 执行提示词（R2）

这是 Personal AI Research OS L1A 的 **Task 9 输入包**。请从零一次处理包根目录下的全部 32 个任务：`task_001` 至 `task_032`。不要读取、参考或复用任何 R1/R2 历史结果、外部报告或包外文件。

严格边界：

1. 对每个任务完整读取其目录内的 `task.yaml`、`AGENT_INSTRUCTION.md`、`evidence.jsonl`、`output_schema.json`、`README.md`、`manifest.json`。只能依据该任务自己的固定 evidence 作答；禁止读取其他任务 evidence、包外资料、网络或任何外部来源。
2. 不得修改任何输入文件。不得联网、安装依赖、访问数据库/模型目录或向 Cognition、Proposal、正式知识库写入任何内容。只能写各任务自己的 `result/`。
3. 预测、估算、目标、情景、市场份额预期及未来年份（例如 `2026E`、`2027E`）不得标为 `supported`；必须保留“预计/预测/估算/约/非官方指引/机构口径”等限定词，并按证据强度标为 `uncertain`、`inference` 或 `hypothesis`。
4. 没有直接因果证据时，不得把相关性、时间顺序或行业叙事写成强因果。应拆分为证据直接支持的事实与明确标为 `inference`/`hypothesis` 的因果解释，并在 rationale 中说明证据边界。
5. `evidence_refs` 必须逐字复制当前任务 `evidence.jsonl` 中的 `chunk_id`，不得引用包外 ID。不得把证据未覆盖的细节写成事实；证据不足须写入 uncertainties、open_questions、additional_evidence_needed。
6. 每个任务必须生成 `task_NNN/result/result.json`、`task_NNN/result/run_meta.json`，自检 Schema、引用成员关系和认识状态后，最后创建 `task_NNN/result/DONE`。无法完成时写 `error.json` + `FAILED`，不要创建 DONE。不得写 CoT。

可以分批处理，但 32 个任务都必须有独立结果。完成后将每个任务的整个 result 内容复制到固定回收路径：

`RETURN/codex-external-golden32-r2/task_NNN/result/`

保持原始 `task_NNN/` 输入目录不变，不要把结果写回原始任务包，不要手工合并 JSON。最后回复 32 个任务各自的完成/失败状态、实际 Worker/模型、结果相对路径以及 RETURN 是否完整。此次仅完成 Task 9；Task 10 的机器评估和人工语义评估必须由本地负责人另行执行，不能宣称 L1A 已完成。
