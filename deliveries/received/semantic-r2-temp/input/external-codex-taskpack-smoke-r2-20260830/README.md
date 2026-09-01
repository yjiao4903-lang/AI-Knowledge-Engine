# External Codex TaskPack Smoke R2

本交付物是 2026-08-30 的外部 Codex R2 smoke 输入包，包含四个固定 Golden 任务：`task_001`、`task_009`、`task_018`、`task_025`。

R2 不得复用 R1 的结果或 runs。外部 Worker 需读取各任务目录内的 canonical `AGENT_INSTRUCTION.md`，只写对应任务的 `result/`，并按 `START_PROMPT.md` 的 RETURN 布局回传三件套：`result.json`、`run_meta.json`、`DONE`。

R1 的机器 Gate 通过不等于语义通过。R2 重点复核预测/估算/未来年份和无直接证据的强因果表述。
