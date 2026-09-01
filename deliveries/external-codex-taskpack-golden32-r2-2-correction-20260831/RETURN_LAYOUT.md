# R2.2 回传布局

外部 Worker 必须将四个任务的完整结果写入：

`RETURN/codex-external-golden32-r2-2-correction/task_NNN/result/`

每个目录必须包含 `result.json`、`run_meta.json`、`DONE`。用户无需手工合并；完成后回传整个 `RETURN` 文件夹。不要覆盖输入包，不要混入旧结果。
