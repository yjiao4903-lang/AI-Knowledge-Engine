# 新窗口启动提示词：I4 Unified Runtime（Window D）

> 使用方法：复制下面整段内容，作为新窗口的第一条消息发送。
> 建议工作目录：D:\AI知识整合体系（集成文档/即将建 runtime）+ D:\AI-Knowledge-Engine + E:\CODEX\AI深度研究\cognition-app。

---

你现在接手 AI Research OS Integration 项目的 I4 Unified Runtime（Window D）。

项目现状：I0-I3 已全部完成并通过 Gate，Integration V1 核心闭环
（Report → Retrieval → Evidence → Proposal → 人工确认 → Cognition）已贯通：

1. AI Knowledge Engine：D:\AI-Knowledge-Engine
   （I0 全量语料 189 篇 / 9780 chunks 一致性 PASS，config.yaml 已是生产全量配置，
   pytest 114，分支 integration/research-os-v1 @ 51d2e76）
2. 个人认知工作台：E:\CODEX\AI深度研究\cognition-app
   （I1 Retrieval Proxy / I2 Reports 融合 / I3 Evidence Bridge 完成，
   分支 integration/research-os-v1 @ 7828306，unit 64 / E2E 15 / 黑盒 10/10）
3. Integration 工作区：D:\AI知识整合体系（docs=事实源，integration_tests=跨系统黑盒）

先完整阅读（按序）：
1. D:\AI-Knowledge-Engine\docs\HANDOFF_I4.md（你的任务契约，含全部基线与启动命令）
2. D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md（整合事实源，I0-I3 交付与 Known Issues）
3. D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md（V1 契约，勿改 Identity 字段）
4. D:\AI-Knowledge-Engine\docs\HANDOFF_PROTOCOL.md（协作与硬约束）

任务：在 D:\AI知识整合体系\runtime\ 交付一键启动/停止/健康检查：
- start.ps1：Docker/Qdrant → KE FastAPI(8765) → 等健康 → cognition start.bat → 等 3220 → 开浏览器；
  PID 记录到 runtime\pids.json
- stop.ps1：按 PID 停止，禁止全局 taskkill node/python；Qdrant 默认保留
- health.ps1：Docker/Qdrant、KE /api/health（含 gpu_worker/index_generation）、
  cognition /api/retrieval/health、:3220，输出 PASS/WARN/FAIL
- 故障策略：GPU 失败→CPU fallback 仍可用（WARN）；Cognition 失败→Startup FAIL
- 日志：D:\AI知识整合体系\logs\integration-YYYYMMDD.log，只记 startup/shutdown/
  health/跨系统故障，轮转 7-14 天

I4 Gate（全过才算完成）：
- 冷状态一键启动成功（Docker 未启也要覆盖）
- stop 干净且不误杀无关进程
- health 三态正确（人为制造一个故障验证）
- GPU→CPU 降级演练（可临时 force_device=cpu）
- cognition unit 64 / E2E 15 / 黑盒 10/10 不下降；KE pytest 114 不下降

核心约束：
- 双库禁止合并；Retrieval 对认知只读；所有正式认知变化经 Proposal Gate；
- 不重写技术栈；ROCm 锁定 torch 2.9.1+rocm7.13.0 不升级；
- **GPU 任务与测试严格串行，禁止并发**（I0 曾因并发索引+测试打满内存卡死）；
- Cognition 启动必须复用真实 start.bat（E:\CODEX\AI深度研究\cognition-app\start.bat），
  不要复制它的 Node 探测/构建逻辑；评估副本 D:\AI知识整合体系\docs\项目整合评估资料_V0.2.md
  只可阅读，不是真实项目；
- 不存在真正 blocker（主计划 §65）就不要停下询问用户。

完成后按 HANDOFF_PROTOCOL 收尾：更新 D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md、
git checkpoint、归档 HANDOFF_I4.md 为 DONE、编写 I5（Backup/Restore/Hardening，
主计划 §43-47）契约。
