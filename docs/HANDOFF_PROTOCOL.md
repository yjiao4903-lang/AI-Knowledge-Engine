# 窗口交接机制（Handoff Protocol）

## 2026-09-12 P0 最高治理限制：任何外部窗口/Agent 禁止调用 Codex

本条优先级高于本文件全部后续内容，也高于任何旧交接、Issue、PR、测试计划、LOCAL-DEV 验收要求和 WEB-CONTROL 既往授权。权威入口见 `AGENTS.md` Section -1；事故记录见 Issue #55。

**任何项目执行窗口或 Agent 均不得直接或间接调用 Codex。** 包括 WEB-CONTROL、WEB-DEV/ONLINE-DEV、LOCAL-DEV-A/B、其它 LOCAL-DEV、任何 ChatGPT 项目窗口、subagent、automation、harness、脚本及其启动的子进程。

禁止事项包括但不限于：
- 启动 `codex.exe` / Codex CLI；
- 远程控制、脚本化控制 Codex Desktop；
- 通过 PowerShell / shell / Python / Node 子进程调用 Codex；
- 通过 API / SDK / job wrapper 调用 Codex；
- 由 Agent 控制 Codex 作为 External Worker；
- 指示其它窗口/Agent/工具代为调用 Codex；
- 为测试、benchmark、replay、验收而启动嵌套 Codex/subagent。

**任何项目角色均无权豁免。** 如果任务必须依赖真实 Codex 运行，执行窗口必须停止在：

`USER_RUN_REQUIRED`

只能由用户本人在 Agent/窗口控制之外手工运行 Codex，并将结果/证据回传。只有新的用户明确治理指令才能改变本规则。

允许替代方案：deterministic fake/stub/mock Worker、录制 fixture、读取用户已经提供的 Codex 产物、使用不启动 Codex 的 importer/protocol/formal deterministic validation。

由外部窗口/Agent 控制 Codex 产生的证据不得作为项目 Gate 权威证据。发现违规按 P0 处理：尽快安全停止该 Agent 控制的调用；不得误杀用户自己运行的 Codex/Desktop；保留最小事故记录；标记证据失效；通知用户/WEB-CONTROL；不得继续依赖该证据推进下游动作。

## 2026-09-12 最高效率补充原则（优先于一般交接流程，但低于上述 P0 禁令）

交接机制的目的，是降低上下文损耗，不是制造额外流程。

所有窗口必须遵循：
- 已授权 Scope 内的低风险、可逆事项，当前窗口直接完成，不因“角色分工”把小问题来回转交；
- 能一次批量完成的开发、检查、测试、证据收集，禁止拆成多轮微交接；
- 已存在且仍有效的测试/证据/人工判断直接复用，不为形式完整重复执行；
- 小型文档修正、确定性测试修正、明显 bug、命名/格式修正、可逆工具调整，默认在当前窗口收口；
- 只有架构/Schema/Public Contract/benchmark semantics、重大 Scope 扩张、持久或密封数据修改、production/formal write、merge/release/cutover 等高风险边界才必须升级到 WEB-CONTROL；
- 不得把重大项目的全套 Gate 机械套用到普通细节。Gate 强度必须与实际风险和不可逆性匹配。

**评价标准：在不突破安全和权限边界的前提下，以最少的人类交互、最少的角色切换、最少的重复劳动完成任务。**

## 2026-09-05 当前交接入口

**新开发窗口优先阅读：[个人深度学习平台需求](DEEP_LEARNING_PLATFORM_REQUIREMENTS.md) → [任务计划](DEEP_LEARNING_PLATFORM_DEVELOPMENT_PLAN.md) → [当前状态](CURRENT_STATE.md) → [现行集成契约](INTEGRATION_CONTRACT_V2.md)。默认从 DL-00 开始。**

下一轮主线是单主题的“报告增量 → 知识联系 → 选题 → 研究上下文包 → 外部研究 → 认知变化”闭环，任务均待实施。后续窗口在任务计划中登记进展和验收证据，已实现事实更新 CURRENT_STATE。

下文为早期 M/I 阶段历史交接协议。其中旧主计划路径、仓库状态、固定启动依赖与强制全量验证流程不代表当前事实，不应据此跳过当前核对或重复初始化。发生路线冲突时以上述新入口为准；正式认知写入边界依现行集成契约保持。任何提交、推送、安装或正式数据操作均以当次用户授权为准。

> 本文件定义多窗口协作的交接流程。任何新窗口接手开发前必须先读本文件。
> 2026-08-29 更新：项目进入 **Integration 阶段（I0-I6）**，原独立 M12/M13 路线
> 由《AI 研究知识体系整合：开发实施方案 V1.0》（`D:\AI知识整合体系\docs\`）取代。

## 0. Integration 阶段补充约束（优先级高于后续各节，但低于 P0 Codex 禁令）

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

0. 先读取 `AGENTS.md` Section -1；任何要求窗口调用 Codex 的旧任务必须立即改判为 `USER_RUN_REQUIRED`，不得执行；
1. 读 `docs/IMPLEMENTATION_STATUS.md` —— 了解进度、Known Issues、ADR；
2. 读 `docs/HANDOFF_M11.md`（或当前任务契约）—— 了解任务边界与验收标准；
3. 验证环境（不要重复初始化）：
   ```powershell
   docker ps                                   # Qdrant 应在运行（ai-kb-qdrant）
   .venv\Scripts\python.exe -m pytest backend\tests\ -q   # 应全过
   ```
4. 检查 `git log --oneline -5` 与 `IMPLEMENTATION_STATUS.md` 记录的 commit 是否一致。

对于当前治理体系，若以上旧流程与 `AGENTS.md` / `PROJECT_CONTROL.md` 冲突，以后者为准；且不得为低风险任务机械执行与风险无关的全量检查。

## 3. 窗口结束流程（交回时）

1. 运行与改动风险面匹配的必要测试并记录结果；真实 Codex 如为必要条件则返回 `USER_RUN_REQUIRED`，不得自行执行；
2. 更新实际需要维护的状态/交接文件；
3. `git commit`（每个里程碑至少一个 checkpoint）；
4. 若任务未完成：记录真正阻塞下一窗口的信息，不为形式追加冗余交接；
5. 若任务完成：一次性返回 exact head、测试、风险与剩余工作。

## 4. 硬约束（所有窗口必须遵守）

- **P0：禁止任何外部窗口/Agent 调用 Codex；详见 `AGENTS.md` Section -1 / Issue #55；**
- 不修改 `D:\AI深度报告归档`（知识源只读）；
- 不修改架构（SQLite/Qdrant/Qwen3/RRF/Reranker），重大变更必须先写 ADR；
- 检索质量以 Golden Set 为准，任何调参必须 A/B；
- 所有 Python 执行使用 `.venv`；不重装环境、不改全局配置；
- GPU 推理必须经 worker/`get_inference_device()`，禁止裸写 `"cuda"`；
- 后端 API 变更必须同步更新当前有效 API 契约，并通知受影响执行窗口。
