# External Codex Smoke R2

这是 R2 重跑，不得复用 R1 的 result、runs 或任何外部结果。请依次处理 `task_001`、`task_009`、`task_018`、`task_025`，每个任务只读取该任务目录输入，并只写入该任务的 `result/`。

严格遵守任务目录中的 `AGENT_INSTRUCTION.md` 和 `output_schema.json`。预测、估算、目标、情景、市场份额预期以及 2026E/2027E 等未来年份不得标为 `supported`；保留原文限定词和来源口径，按证据强度使用 `inference`、`hypothesis` 或 `uncertain`。没有直接因果证据时，不得把相关性或时间顺序改写为强因果。

每个任务完成后写入 `result/result.json`、`result/run_meta.json`，确认自检完成后最后创建 `result/DONE`。不要修改任何输入文件。完成结果请按以下布局回传：`RETURN/codex-external-smoke-r2/task_NNN/result/`。
