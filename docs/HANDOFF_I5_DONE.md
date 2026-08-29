# I5 交接契约：Backup / Restore / Hardening（Window E）【已完成】

> 状态：**DONE（2026-08-30）** ｜ 交接方：Window D（I4 Lead）→ 执行方：Window E

## 完成记录（Window E，2026-08-30）

- 交付：`D:\AI知识整合体系\runtime\{backup,restore}.ps1`（Tier1 认知 Markdown 全量 + 逐文件
  sha256 manifest；Tier2 版本化资产快照；Tier3 重建命令记录；Tier4 可选 Qdrant Snapshot）；
  `golden_queries.jsonl` 补入整合 git 版本管理；runtime/README.md 追加用法。**两 Core 零改动**。
- **I5 Gate 全 PASS**：
  - Backup：Tier1 全量 + manifest VerifyOnly/VerifyAfter 独立校验 PASS；
  - Restore：隔离副本真实演练（备份→删除 3 个正式认知对象 133→130→恢复→独立 sha256 全量比对
    **133 一致 / 0 缺失 / 0 不符**→副本重建派生索引 **38/38 文件、notes 37 行**）；未触碰真实认知目录；
  - Offline：停 Qdrant 下 KE degraded 存活、**lexical 纯 FTS 可用**、hybrid 明确 503 QDRANT_ERROR、
    Cognition 自动 legacy_substring 降级；恢复后全栈 PASS；
  - Index Rebuild：`reindex.py check` 四方一致 9780 + 副本派生索引重建；
  - Cognition Data Intact ✅；Unified Health（health.ps1 全绿）✅。
- 回归：KE pytest dev 配置 **114 passed**；cognition unit **64/64**、E2E **15/0**、黑盒 **10/10**；
  Golden 引用 I4 复验一致（0.920/0.765/0.801，I5 未改 KE 检索代码）。
- 新 Known Issues：见整合 IMPLEMENTATION_STATUS #19-21（qdrant 中断后需重启 KE 恢复 dense；
  Tier1 排除项；golden_queries.jsonl 版本管理补录）。
- 收尾：整合 IMPLEMENTATION_STATUS 已更新；本契约归档为 HANDOFF_I5_DONE.md；
  I6 契约 `docs/HANDOFF_I6.md` 已起草。

---

> 交接日期：2026-08-30 ｜ 交接方：Window D（I4 Lead）｜ I4 已完成并归档
> 依据：主计划 §43-47、补充方案 §34 可选加分；I0-I4 全部完成
> 新窗口首读：本文件 → `D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md` →
> `D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md` →
> `D:\AI知识整合体系\docs\PROJECT_HANDOFF_COMPENDIUM.md`（Window C 接力交接包，长期有效）

## 0. 继承资产与基线（已验证，勿重做）

| 资产 | 状态 |
|---|---|
| KE（D:\AI-Knowledge-Engine） | I0 完成：189 篇 / 9780 chunks；config.yaml=生产全量；Golden 0.920/0.765/0.801（I4 复验一致）；commit `51d2e76`+（docs @ integration/research-os-v1） |
| cognition-app（E:\CODEX\AI深度研究\cognition-app） | I1-I3 完成：Retrieval Proxy + Reports 融合 + Evidence Bridge；unit 64 / E2E 15 / 黑盒 10/10（I4 复验一致）；commit `7828306` |
| Unified Runtime（I4） | `D:\AI知识整合体系\runtime\`：start.ps1 / stop.ps1 / health.ps1（一键启停/健康三态 PASS-WARN-FAIL，退出码 0/0/1）+ pids.json + 14 天轮转整合日志；集成工作区已入 git |
| 数据价值分层（主计划 §43） | Tier1 认知 Markdown（cognition/ 下 Questions/Judgments/Topics/Projects/Proposals/Rewiews/Reading Records/Config）必须备份；Tier2 版本管理（Golden/Tech Terms/Integration Config/ADR/Schemas）；Tier3 可重建（Retrieval SQLite/FTS/Qdrant/Embedding Index）；Tier4 可选 Qdrant Snapshot（加速恢复，非唯一备份） |
| cognition 内建能力 | `server/backup.js` BackupManager：`POST /api/backup` + 设置页「立即备份 / 恢复」（I5 可优先复用/审计，勿重复造轮子） |
| 已知基线问题 | 整合 Known Issues #14（3 条 M5/M6 陈旧断言 prod 配置失败，dev 配置 114 过）、#15（CPU 降级 hybrid_rerank 走 legacy fallback，dense 可用）——I5 不强制修复，但要写入 I5 的 Offline Test 预期 |

## 1. 任务范围（主计划 §43-47）

### I5A Backup（Tier 1 必须 + Tier 2 版本管理）
1. **Tier 1**：备份 cognition 认知数据全套（cognition/ 目录：问题/判断/主题/项目/提案/复盘/
   阅读记录/Config），不得只备份 SQLite 派生库——Markdown 是唯一事实源；
   back-up 至 `D:\AI知识整合体系\backups\`（或等价受控位置），带时间戳 + 校验（sha256 manifest）。
2. **Tier 2**：把下列纳入版本管理（建议并入已 init 的 `D:\AI知识整合体系` git 仓库或既有仓库）：
   Golden Query Set、Tech Terms、Integration Config（runtime/ 与 config/）、ADR、Schemas。
3. **Tier 3**：明确记录"可重建"清单与重建命令（源自 I0/I4 已验证命令，勿发明新流程）；
   不备份或仅弱备份 KB SQLite/FTS/Qdrant。
4. **Tier 4（可选）**：Qdrant Snapshot（`curl POST /collections/{c}/snapshots` 或 docker exec），
   作为加速恢复的可选产物，必须注明"非唯一备份"。

### I5B Restore Drill（必须真实演练，主计划 §44）
```text
Backup → 破坏测试环境 → Restore → Reindex → Health → Search → Cognition Data Check
```
- 破坏手段建议：删除 cognition 目录部分正式文件 / 关闭认知目录重建派生 SQLite / 清空 Qdrant collection；
  **必须在隔离副本或可恢复结果完成后再真实验证**（严禁直接对真实认知数据执行破坏性演练；
  认知数据不在 git 中，破坏不可撤销——用备份副本演练后 Restore 回真环境）；
- Restore Drill 必须产出证据（命令输出/前后对比），不允许纸上谈兵；
- Cognition Data Check：恢复后用 `unit 64 / E2E 15 / 黑盒 10/10` 冒烟 + 抽查正式认知对象完整。

### I5C Offline Test（主计划 §45）
- 断网（停 Docker/宿主断网模拟可选）下 Search / Rerank / Cognition / Proposal 仍可用：
  验证模型已本地化（D:/AI-Models 离线加载）、PID/服务不依赖外网（npm install 已缓存、无在线检查）；
- 记录离线启动路径（可复用 runtime/start.ps1，但 Docker 不可用时需文档化替代）；
- 产出 Offline 结论：可用/部分可用/不可用 + 证据。

### I5D I5 Gate（主计划 §47，全过才算完成）
```text
[ ] Backup PASS（Tier1 完整 + manifest 校验通过）
[ ] Restore PASS（真实演练：破坏→恢复→Health/Search/Cognition Data 全过）
[ ] Offline PASS（断网下 Search/Rerank/Cognition/Proposal 可用）
[ ] Index Rebuild PASS（重建命令可复现，四方一致 9780）
[ ] Cognition Data Intact（恢复后 formal 认知对象与备份一致）
[ ] Unified Health PASS（runtime/health.ps1 全绿或仅预期内 WARN）
```

## 2. 硬约束（延续全部此前契约）

- 双库禁止合并；Retrieval 禁写认知；Proposal Gate 不可绕过；不重写技术栈；
  ROCm 锁定 torch 2.9.1+rocm7.13.0；GPU 任务与测试严格串行（I0 事故教训）；
- **认知数据不在任何 git 仓库中——Tier1 备份与 Restore Drill 必须先副本后操作**；
  禁止在真实认知目录上执行破坏性演练（除非演练即破坏本身且已有完整备份并记录恢复步骤）；
- One-Writer：I5 期间只写 backup/restore 工具 + Integration 配置；改两 Core 需先在本契约登记理由；
- Cognition 启动必须复用真实 start.bat；runtime 脚本若需修改，属 I4 资产维护（在 runtime/ 内改，
  更新 README 与整合 Known Issues）；禁止 taskkill /IM 全局射杀。
- 交付格式（主计划 §64）：Code Changes / Files / Commands / Tests / Results /
  Known Issues / ADR / Commit / Next。

## 3. 可选加分项

- Golden Smoke Set（补充方案 §34）：从 50 条 Golden 抽 ~10 条做快速冒烟（数据增量后只跑 Smoke）。

## 4. 完成收尾

按 HANDOFF_PROTOCOL：更新 `D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md`（含 I5 摘要、
Known Issues、本窗口 commit hash）→ git checkpoint（集成工作区 + KE docs 镜像）→
归档本契约为 HANDOFF_I5_DONE.md → 编写 I6（Cognition Read-only Semantic Search，主计划 §48-49）
契约。