# 窗口交接机制（Handoff Protocol）

> 本文件定义多窗口协作的交接流程。任何新窗口接手开发前必须先读本文件。
> 2026-08-29 更新：项目进入 **Integration 阶段（I0-I6）**，原独立 M12/M13 路线
> 由《AI 研究知识体系整合：开发实施方案 V1.0》（`D:\AI知识整合体系\docs\`）取代。

## 0. Integration 阶段补充约束（优先级高于后续各节）

1. **双仓库**：`D:\AI-Knowledge-Engine`（本仓库）与
   `E:\CODEX\AI深度研究\cognition-app` 保持独立，禁止合并（注意：实测
   cognition-app 尚无 git，首次修改前须 init + 初始 commit）；
2. **评估副本 ≠ 真实项目**：`D:\AI知识整合体系\docs\项目整合评估资料_V0.2.md`
   只可阅读；修改/测试/启动 cognition-app 必须进入真实目录，入口 start.bat；
3. **集成工作区**：`D:\AI知识整合体系\`（docs/runtime/config/logs）；
   集成事实源为该目录下 `docs\IMPLEMENTATION_STATUS.md`；
4. **永久职责边界**：Cognition App 拥有唯一认知写入权（Proposal Gate）；
   Knowledge Engine 对认知数据只读；两库禁止合并，跨系统只走 HTTP API；
5. **路线**：I0（Full Corpus+Contract）→ I1 Proxy → I2 Reports 融合 →
   I3 Evidence Bridge → I4 Unified Runtime → I5 Backup/Hardening → I6；
6. 每阶段任务契约：`HANDOFF_I0.md`（当前）、后续 HANDOFF_I1.md...；
   里程碑统一交付格式见主计划 §64。

---

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
