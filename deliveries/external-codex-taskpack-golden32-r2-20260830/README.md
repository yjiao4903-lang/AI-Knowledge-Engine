# External Codex Golden32 R2 Task 9 输入包

这是 32 个固定 TaskPack 的只读输入副本，用于收集外部 Worker 结果。它只是 L1A Task 9 输入包，不包含任何历史 R1/R2 结果；外部执行完成后仍必须进行 Task 10 机器 Gate 和人工语义评估，不能据此宣称 L1A 完成。

## 三步操作

1. 解压 ZIP，并保持包根目录以及 `task_001/` 至 `task_032/` 目录结构不变。
2. 将 [START_PROMPT.md](START_PROMPT.md) 整段复制给外部 Codex，让它在包根目录处理全部 32 个任务；不要让它读取包外资料。
3. 确认外部窗口将结果放入 `RETURN/codex-external-golden32-r2/task_NNN/result/` 后，把整个 `RETURN/` 文件夹带回本地。无需手工合并，也不要修改原始任务目录。

回收结构见 [RETURN_LAYOUT.md](RETURN_LAYOUT.md)。
