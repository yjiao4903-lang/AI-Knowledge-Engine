# TaskPack 任务说明

这是一个 Personal AI Research OS 的标准 TaskPack。
你的工作目录就是本任务目录（当前目录）。

## 使用步骤

1. 用 Trae / Codex / Claude Code 打开本目录；
2. 复制下面的启动提示词并发送；
3. 等待 Agent 生成完成；
4. 确认 `result/DONE` 已创建；
5. 返回 Research OS，点击“刷新”读取结果。

## 启动提示词

```text
请读取当前目录中的 AGENT_INSTRUCTION.md，并严格执行当前 TaskPack。
只允许读取当前任务目录，输入文件只读，只允许写 result/。
完成后必须生成 result/result.json、result/run_meta.json，并最后创建 result/DONE。
```

## 输入层次

标准输入始终包含 `task.yaml`、`evidence.jsonl`、`output_schema.json` 等文件。
Dossier-backed 研究任务还可能包含：

- `research_brief.md`：人可读的长期方向、主题当前状态、本次任务边界；
- `research_context.json`：上述上下文的稳定 ID / source version 结构化快照；
- `cognition_context.jsonl`：用户显式选择的正式 Cognition 对象只读快照。

Research Context / Cognition Context 不是事实证据。事实性 claim 只能由 `evidence.jsonl` 支撑。

## 说明

- 所有输入文件全部只读，不得修改；
- 唯一允许写入的是 `result/` 目录；
- 语义口径：预测、估算、目标、情景、市场份额预期及未来年份（如 2026E/2027E）不得标为 `supported`；保留原文限定词和来源口径，按证据强度标为 `inference`、`hypothesis` 或 `uncertain`。没有直接因果证据时，不得把相关性或时间顺序写成强因果。
- `manifest.json` 记录全部实际输入文件的 sha256，任何输入被改动都会导致结果被拒绝导入；
- 完成标志是 `result/DONE`（必须最后创建）；无法完成时写 `result/error.json` 并创建 `result/FAILED`，不要创建 `DONE`。
