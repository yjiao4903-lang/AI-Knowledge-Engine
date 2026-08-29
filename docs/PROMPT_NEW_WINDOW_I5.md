# 新窗口启动提示词：I5 Backup / Restore / Hardening（Window E）

> 使用方法：复制下面整段内容，作为新窗口的第一条消息发送。
> 建议工作目录：D:\AI-Knowledge-Engine + D:\AI知识整合体系 + E:\CODEX\AI深度研究\cognition-app。

---

你现在接手 AI Research OS Integration 项目的 I5 Backup/Restore/Hardening（Window E）。

项目现状：I0-I4 已全部完成并通过 Gate，Integration V1 核心闭环已贯通，且
一键运行时（Unified Runtime）已交付：

1. AI Knowledge Engine：D:\AI-Knowledge-Engine
   （I0 全量语料 189 篇 / 9780 chunks 一致性 PASS；Golden 0.920/0.765/0.801 与 I0 逐位一致；
   pytest：dev 配置 114 全过（README/status 有说明），prod 配置 3 条 M5/M6 陈旧断言失败
   ——见整合 Known Issues #14，非 I4 回归；分支 integration/research-os-v1）
2. 个人认知工作台：E:\CODEX\AI深度研究\cognition-app
   （I1-I3 完成，unit 64 / E2E 15 / 黑盒 10/10；分支 integration/research-os-v1 @ 7828306）
3. Unified Runtime：D:\AI知识整合体系\runtime（start.ps1 / stop.ps1 / health.ps1 + pids.json，
   一键启停全栈 + 健康三态；整合工作区已 init git）
4. Integration 工作区：D:\AI知识整合体系（docs=事实源，runtime=运行时，integration_tests=黑盒）

先完整阅读（按序）：
1. D:\AI-Knowledge-Engine\docs\HANDOFF_I5.md（你的任务契约，含数据分层与 I5 Gate）
2. D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md（整合事实源，I0-I4 交付与 Known Issues）
3. D:\AI知识整合体系\docs\PROJECT_HANDOFF_COMPENDIUM.md（Window C 接力交接包，长期有效）
4. D:\AI-Knowledge-Engine\docs\HANDOFF_PROTOCOL.md（协作与硬约束）
5. D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md（V1 契约，勿改 Identity 字段）

任务（主计划 §43-47）：
- Backup：Tier1 认知 Markdown（cognition/ 下问题/判断/主题/项目/提案/复盘/阅读/Config）必备份，
  带时间戳 + sha256 manifest；Tier2 版本管理（Golden/Tech Terms/Integration Config/ADR/Schemas，
  可并入 D:\AI知识整合体系 git 仓库）；Tier3 可重建（SQLite/FTS/Qdrant）只记录重建命令；
  Tier4 可选 Qdrant Snapshot
- Restore Drill：必须真实演练（Backup → 副本上破坏 → Restore → Reindex → Health → Search →
  Cognition Data Check），优先复用 cognition 内建 /api/backup 并审计；
  **认知数据不在 git，破坏性演练必须在备份副本上做**，严禁直接毁真数据
- Offline Test：断网下 Search/Rerank/Cognition/Proposal 可用性（模型已本地化 D:/AI-Models）
- I5 Gate（全过才算）：Backup PASS / Restore PASS / Offline PASS / Index Rebuild PASS /
  Cognition Data Intact / Unified Health PASS

核心约束：
- 双库禁止合并；Retrieval 对认知只读；所有正式认知变化经 Proposal Gate；
- 不重写技术栈；ROCm 锁定 torch 2.9.1+rocm7.13.0 不升级；
- **GPU 任务与测试严格串行，禁止并发**（I0 曾因并发索引+测试打满内存卡死）；
- Cognition 启动必须复用真实 start.bat；runtime/ 脚本修改属 I4 资产维护（原地改 + 更新 README）；
- 不存在真正 blocker（主计划 §65）就不要停下询问用户。

完成后按 HANDOFF_PROTOCOL 收尾：更新 D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md、
git checkpoint（集成工作区 + KE docs）、归档 HANDOFF_I5.md 为 DONE、编写 I6
（Cognition Read-only Semantic Search，主计划 §48-49）契约。