# 新窗口启动提示词：I0 Full Corpus Gate + Integration Contract

> 使用方法：复制下面整段内容，作为新窗口的第一条消息发送。
> 新窗口建议工作目录：D:\AI知识整合体系（集成文档）+ D:\AI-Knowledge-Engine（检索代码）。

---

你现在接手 AI Research OS Integration 项目。

当前有两个成熟系统：

1. AI Knowledge Engine：D:\AI-Knowledge-Engine（M0-M11 完成，pytest 102 passed，
   Retrieval Quality Gate 5/5 PASS，详见 docs/IMPLEMENTATION_STATUS.md）
2. 原个人认知工作台：E:\CODEX\AI深度研究\cognition-app

特别注意：

D:\AI知识整合体系\docs\项目整合评估资料_V0.2.md 只是原工作台的评估资料副本。
如果只是做体系评估，可以读取这个副本。如果需要修改、测试、启动、运行、构建或检查 Git，
必须进入 E:\CODEX\AI深度研究\cognition-app（原工作台标准启动入口 start.bat）。
不要把评估资料副本当成真实项目。

先完整阅读《AI 研究知识体系整合：开发实施方案 V1.0》
（D:\AI知识整合体系\docs\AI研究知识体系整合_开发实施方案_V1.0.md），
以及 D:\AI-Knowledge-Engine\docs\ 下的 HANDOFF_PROTOCOL.md 与 HANDOFF_I0.md
（I0 任务契约，含交接方已核实的资产状态与工程要点）、IMPLEMENTATION_STATUS.md、
M9_GOLDEN_EVALUATION.md、PROJECT_EVALUATION_REPORT.md。

当前不要重做 M0-M11。Retrieval Core 已通过 Quality Gate。原独立 M12/M13 路线取消，
改为整合路线 I0-I6。你从 I0 开始。

已知就绪性事实（交接方实测，已写入 HANDOFF_I0.md §0）：
- cognition-app 目录与代码存在但尚无 git 仓库（首次修改前先 git init + 初始 commit）；
- D:\AI知识整合体系\docs 已有实施方案与评估资料，runtime/config/logs 尚未创建；
- KE 当前索引为 dev 语料（10 篇），config roots 指向 data/dev_kb。

第一轮只读执行（不修改代码）：
1. 阅读 Knowledge Engine IMPLEMENTATION_STATUS / M9 Golden Evaluation；
2. 阅读 Cognition Assessment Copy（评估副本）；
3. 检查两个真实项目的目录与服务状态；
4. 生成 D:\AI知识整合体系\docs\INTEGRATION_READINESS.md
   （Repo status / Branch / Service status / Retrieval version / Cognition version /
   Known conflicts / Full Corpus status / Contract gaps）。

随后立即执行 I0（任务契约 = docs/HANDOFF_I0.md，严格按其 §1 顺序）：
1. 切换 KE 索引目标到 D:\AI深度报告归档，执行 Full Corpus Index
   （backend/scripts/reindex.py scan，预计 1-3 小时）；
2. 生成 FULL_CORPUS_REPORT.md + full_corpus_stats.json + full_corpus_failures.json；
3. 一致性 Gate：chunks = fts_terms = fts_trigram = qdrant_points（reindex.py check）；
4. 全库随机抽样 ≥50 篇人工核对；
5. 在全量索引上重跑 50 条 Golden Regression（新建 full_corpus_regression.py）；
6. 补齐 GET /api/documents/{id}/chunks 并固化 API 测试；
7. 落地 Integration Contract V1 + EvidenceReference V1
   （写入 D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md）；
8. 固定 Health / Error Model；
9. 更新两份 IMPLEMENTATION_STATUS.md，git checkpoint（两仓库各自提交，
   分支 integration/research-os-v1）。

I0 Gate（HANDOFF_I0.md §2）全部满足后才能进入 I1：Cognition Retrieval Proxy。

核心约束：
- 两个数据库禁止合并；Retrieval 禁止写 Cognition Markdown；
- 所有正式认知变化继续经过 Proposal + Preview + Apply；
- I0 期间不修改 Cognition App；
- React Retrieval UI 保留为 Debug Console；Vue Cognition App 是正式产品入口；
- 不重写已有技术栈；ROCm/PyTorch 版本锁定不升级；
- 测试基线 102 passed 只增不减；注意解耦 test_api 对 dev catalog 的依赖
  （HANDOFF_I0.md §3）；
- 如果不存在真正 blocker（见主计划 §65），不要停下来询问用户。
