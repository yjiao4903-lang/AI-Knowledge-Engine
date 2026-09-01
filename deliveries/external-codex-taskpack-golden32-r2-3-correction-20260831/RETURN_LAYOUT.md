# R2.3 回传布局

外部 Worker 必须将完整结果写入：

`RETURN/codex-external-golden32-r2-3-correction/task_NNN/result/`

每个任务必须包含 `result.json`、`run_meta.json`、`DONE`。用户无需手工合并；完成后回传整个 `RETURN` 文件夹，不得混入旧结果或覆盖输入包。
