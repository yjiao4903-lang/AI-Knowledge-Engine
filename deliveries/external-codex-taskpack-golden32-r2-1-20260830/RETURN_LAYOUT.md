# R2.1 回传布局

外部窗口必须保持输入包不变，并将输出放在：

`RETURN/codex-external-golden32-r2-1/task_NNN/result/`

每个 `task_NNN` 必须包含：

- `result.json`
- `run_meta.json`
- `DONE`

用户无需手工合并。完成后将整个 `RETURN` 文件夹压缩并带回本地；不要覆盖本输入包，也不要把旧 R1/R2 结果混入新目录。
