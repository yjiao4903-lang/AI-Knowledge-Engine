# R2.1 task_018 因果认识修正包

这是针对 R2 task_018 的单任务重跑包。包内只含当前 R2 canonical 输入，不含 R1/R2 历史结果；目标是修正强因果、未来预测和估算口径。

## 操作

1. 解压 ZIP，保持 `task_018/` 和包根结构不变。
2. 将 [START_PROMPT.md](START_PROMPT.md) 整段复制给外部 Codex，让它在包根目录从零执行。
3. 确认结果位于 `RETURN/codex-external-smoke-r2-1/task_018/result/` 后，把整个 `RETURN/` 文件夹带回本地；无需手工合并，也不要改动原始输入。

本包结果仍需本地 Importer 和人工语义复核，不等于最终 PASS。
