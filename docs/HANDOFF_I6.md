# I6 交接契约：Cognition Read-only Semantic Search（Window F，可选）

> 状态：**待 Window F 接手（2026-08-30 起草）** ｜ 交接方：Window E（I5 Lead）
> 依据：主计划 §48-50；I0-I5 全部完成并归档
> 新窗口首读：本文件 → `D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md` →
> `D:\AI知识整合体系\docs\PROJECT_HANDOFF_COMPENDIUM.md`（长期有效）

## 0. 继承资产与基线（已验证，勿重做）

| 资产 | 状态 |
|---|---|
| KE（D:\AI-Knowledge-Engine） | I0-I5：189 篇 / 9780 chunks 一致；pytest dev 114；Golden 0.920/0.765/0.801；分支 integration/research-os-v1 |
| cognition-app（E:\CODEX\AI深度研究\cognition-app） | I1-I3：Retrieval Proxy + Reports 融合 + Evidence Bridge；unit 64 / E2E 15 / 黑盒 10/10；commit `7828306` |
| Unified Runtime（I4）+ Backup/Restore（I5） | `D:\AI知识整合体系\runtime\{start,stop,health,backup,restore}.ps1`；Tier1 备份 manifest sha256 + Restore Drill 已验证 |
| 认知数据 | `E:\CODEX\AI深度研究\cognition`（Markdown 唯一事实源，不在 git；Tier1 备份由 backup.ps1 负责） |
| 已知基线问题 | 整合 Known Issues #14（prod 3 条 M5/M6 陈旧断言）、#15（CPU 降级性能）、#19（qdrant 中断需重启 KE）等 |

## 1. 任务范围（主计划 §48-50）

> I6 为**可选项**，仅当负责人决定启动时执行；默认不索引候选内容。

### I6A KE 侧：Cognition 第二类 Source（只读）
1. 新增独立 collection **`kb_cognition_chunks_v1`**（与报告 `kb_chunks_full_v1` 分开，禁止混用）；
2. 新增只读 ingest 管线：扫描 `E:\CODEX\AI深度研究\cognition` 下正式认知 Markdown
   （复用现有 parser/chunker/embedding，不改技术栈）；
3. **默认索引对象**：Question / Judgment / Topic / Project / Reading Record / Review；
   **默认不索引**：Pending Proposal / Inbox / Rejected Candidate（避免候选内容看起来像正式认知，
   主计划 §49）；
4. **READ ONLY 硬约束**：KE 对该 Source 只读，绝不写认知（含 Proposal/Apply）；索引由 KE 侧
   单独触发（reindex/scan 新命令），不依赖 cognition 写路径；
5. 契约与证据引用：认知检索结果以 Cognition Markdown 为源，EvidenceReference 的
   `source_type` 增加认知类型（改契约 Identity 前必须先 ADR，主计划 §66）。

### I6B Cognition 侧：检索入口（复用既有 Proxy）
1. 复用 I1 Retrieval Proxy 模式：新增 `/api/retrieval/cognition-search`（或扩展 search 加
   scope 参数），Node 仍只做转发/降级，不做检索智能；
2. 未来统一 Search Scope（主计划 §50）：全部 / 研究报告 / 我的正式认知，候选内容如需检索
   单独 scope 并明显标识；
3. fallback 矩阵沿用 I1（UNAVAILABLE/TIMEOUT/BAD_RESPONSE→legacy 降级；空结果不降级）。

## 2. I6 Gate（建议，启动前由负责人确认）

```text
[ ] kb_cognition_chunks_v1 与报告 collection 物理隔离（独立 collection 实测）
[ ] 默认索引对象与排除对象正确（不索引 Pending Proposal/Inbox/Rejected）
[ ] KE 对认知 READ ONLY 验证（索引/检索不产生任何写路径）
[ ] Cognition 语义检索可用（检索命中正式认知对象，结果带来源标识）
[ ] 回归不下降：KE pytest 114 / cog 64+15 / 黑盒 10/10 / Golden 不变
[ ] Unified Health 纳入新 collection 状态
```

## 3. 硬约束（延续全部此前契约）

- 双库禁止合并；Retrieval 对认知只读；Proposal Gate 不可绕过；不重写技术栈；
- ROCm 锁定 torch 2.9.1+rocm7.13.0；GPU 任务与测试严格串行（I0 事故教训）；
- 认知数据不在 git——I6 索引为只读消费，任何写操作须先 ADR 并经负责人批准；
- One-Writer：I6 窗口只写 KE 新增模块 + cognition 只读代理；改既有模块先在本契约登记理由；
- Cognition 启动必须复用真实 start.bat；runtime 脚本修改属 I4/I5 资产维护（原地改 + 更新 README）。

## 4. 可选加分项

- Cognition Search Scope 统一入口（主计划 §50 三档：全部/研究报告/我的正式认知）。

## 5. 完成收尾

按 HANDOFF_PROTOCOL：更新 `D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md`（含 I6 摘要、
Known Issues、commit hash）→ git checkpoint（整合工作区 + KE docs）→ 归档本契约为
HANDOFF_I6_DONE.md → 之后阶段（V3 等）按主计划路线推进。
