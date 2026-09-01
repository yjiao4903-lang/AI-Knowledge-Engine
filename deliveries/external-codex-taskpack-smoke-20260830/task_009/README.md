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

## 说明

- 输入文件（`task.yaml` / `AGENT_INSTRUCTION.md` / `evidence.jsonl` / `output_schema.json` / `manifest.json`，以及可能存在的 `cognition_context.jsonl`）全部只读，不得修改；
- 唯一允许写入的是 `result/` 目录；
- `manifest.json` 记录了全部输入文件的 sha256，任何输入被改动都会导致结果被拒绝导入；
- 完成标志是 `result/DONE`（必须最后创建）；无法完成时写 `result/error.json` 并创建 `result/FAILED`，不要创建 `DONE`。
