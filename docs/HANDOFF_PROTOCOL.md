# 窗口交接机制（Handoff Protocol）

> 本文件定义多窗口协作的交接流程。任何新窗口接手开发前必须先读本文件。

## 1. 事实源（Single Source of Truth）

| 文件 | 作用 |
|---|---|
| `docs/IMPLEMENTATION_STATUS.md` | **项目进度唯一事实源**。每窗口结束时必须更新（里程碑、测试数、Known Issues、ADR、最新 commit hash） |
| `docs/HANDOFF_M11.md` | 当前窗口的任务契约（M11 前端）。接手窗口的第一份必读文件 |
| `docs/M9_GOLDEN_EVALUATION.md` 等 | 各里程碑评测报告（改动检索行为前必读对应报告） |
| `data/golden_queries.jsonl` | 50 条人工标注 Golden Set。**不允许未经 ADR 修改** |
| `docs/DEVELOPMENT_ADDENDUM_*.md` | 用户下发的阶段开发计划（约束来源） |

## 2. 窗口接手流程（新窗口启动时）

1. 读 `docs/IMPLEMENTATION_STATUS.md` —— 了解进度、Known Issues、ADR；
2. 读 `docs/HANDOFF_M11.md`（或当前任务契约）—— 了解任务边界与验收标准；
3. 验证环境（不要重复初始化）：
   ```powershell
   docker ps                                   # Qdrant 应在运行（ai-kb-qdrant）
   .venv\Scripts\python.exe -m pytest backend\tests\ -q   # 应全过
   ```
4. 检查 `git log --oneline -5` 与 `IMPLEMENTATION_STATUS.md` 记录的 commit 是否一致。

## 3. 窗口结束流程（交回时）

1. 运行全部测试并记录结果；
2. 更新 `IMPLEMENTATION_STATUS.md`（完成项、测试数、新 Known Issues、ADR、本窗口最后 commit hash）；
3. `git commit`（每个里程碑至少一个 checkpoint）；
4. 若任务未完成：在任务契约文件末尾追加「当前状态与剩余工作」小节，让下一窗口无缝接手；
5. 若任务完成：把 `HANDOFF_M11.md` 重命名为 `HANDOFF_M11_DONE.md`（或归档到 docs/archive/），并编写下一窗口的任务契约。

## 4. 硬约束（所有窗口必须遵守）

- 不修改 `D:\AI深度报告归档`（知识源只读）；
- 不修改架构（SQLite/Qdrant/Qwen3/RRF/Reranker），重大变更必须先写 ADR；
- 检索质量以 Golden Set 为准，任何调参必须 A/B；
- 所有 Python 执行使用 `.venv`；不重装环境、不改全局配置；
- GPU 推理必须经 worker/`get_inference_device()`，禁止裸写 `"cuda"`；
- 后端 API 变更必须同步更新 `docs/HANDOFF_M11.md` 中的 API 契约（若前端窗口已接手，需在其 Known Issues 中通知）。
