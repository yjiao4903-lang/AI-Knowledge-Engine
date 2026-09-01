# External Codex TaskPack Smoke 包

这是四个外部 Worker smoke 输入包的只读副本：`task_001`、`task_009`、`task_018`、`task_025`。包内不含模型、数据库、源代码或已有外部结果。

## 三步操作

1. 解压本包，并保持四个 `task_NNN/` 目录和包根目录结构不变。
2. 将 [START_PROMPT.md](START_PROMPT.md) 整段复制到外部 Codex 窗口，让它在本包根目录工作；外部窗口只能读包内 evidence，并按提示生成每个任务的 result 三件套。
3. 确认外部窗口已把结果放入 `RETURN/codex-external-smoke/task_NNN/result/` 后，把整个 `RETURN/` 文件夹带回本地。无需手工合并结果，也不要修改原始任务目录。

详细返回路径见 [RETURN_LAYOUT.md](RETURN_LAYOUT.md)。本包只支持 smoke 输入交付；四任务结果需要本地 Importer 复核，不能凭外部窗口回复直接判 PASS。
