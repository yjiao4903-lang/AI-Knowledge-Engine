# Personal AI Research OS 整合项目 — 对外审核评估报告

> **文档性质**：交付外部审核员的项目进度总结，对照主开发计划 V1.0 逐项核对。
> **as-of 日期**：2026-08-30 ｜ **审核范围**：Integration 阶段 I0–I6（含底层 Retrieval M0–M11）
> **主计划基准**：`D:\AI知识整合体系\docs\AI研究知识体系整合_开发实施方案_V1.0.md`
> **唯一进度事实源**：`D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md`
> **集成契约 / 交接归档**：`D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md`、`D:\AI-Knowledge-Engine\docs\HANDOFF_I6_DONE.md`（及 I0-I5 DONE）
>
> **可复现性声明**：本报告所有"通过/完成"结论均可在本机按其标注的测试命令复现，非仅页面打开/API 200/编译通过的"宣称式完成"（主计划 §63）。

---

## 1. 项目定位与目标（对照主计划 §0 / §69）

根据主计划，两套系统**不合并代码库、数据库、后端**，整合为单一产品：

- **Cognition App**（Vue，`E:\CODEX\AI深度研究\cognition-app`）= **Personal Research OS 的 Cognition Control Plane**，拥有**唯一正式认知写入权限**。
- **AI Knowledge Engine**（`D:\AI-Knowledge-Engine`）= **Evidence Engine**，提供 Parser/Chunker/FTS/Dense/Hybrid/Reranker/Qdrant/Search API，**对认知层只读**。
- 两系统以 **API / EvidenceReference** 为唯一正式整合边界；正式认知写入统一走 Cognition、经 Human Confirmation，`Report→Retrieval→Evidence→Proposal→Human Confirmation→Cognition Update` 核心链不可破坏。

**目标形态**：两项目代码独立 / 数据独立 / 职责独立，入口统一 / Evidence 契约统一 / 正式认知写入统一。

---

## 2. 开发路线完成总览（对照主计划 §9 / §68）

主计划路线：`M0–M11` → `I0 → I1 → I2 → I3 → I4 → I5` → `Integration V1 Stable` → `I6` → `Future (LLM/MCP/Agent)`。

| 阶段 | 计划目标 | 实际状态 | 关键 Gate 结论 |
|---|---|---|---|
| M0–M11 | 既有 Retrieval（报告引擎） | ✅ 完成（开发史既定） | pytest 基线 102 → I0 后 114 |
| **I0** | Full Corpus + Integration Contract | ✅ 完成 | 全库 Gate 全 PASS |
| **I1** | Cognition Retrieval Proxy | ✅ 完成 | 回归 PASS |
| **I2** | Cognition Reports Search 融合 | ✅ 完成 | GUI 冒烟七项 PASS |
| **I3** | Evidence → Proposal Bridge | ✅ 完成 | Proposal Gate PASS |
| **I4** | Unified Runtime | ✅ 完成 | One-click PASS |
| **I5** | Backup / Restore / Hardening | ✅ 完成 | Restore PASS |
| **Integration V1 Stable** | I0–I5 稳定基座 | ✅ 达成 | Def-of-Done 全项满足（见 §6） |
| **I6** | Cognition Read-only Semantic Search（可选） | ✅ 完成 | Gate 六项 PASS |
| Future | LLM Synthesis / MCP / Agent | ⬜ 未启动 | 属路线图后段，不在当前交付 |

**结论：主计划 I0–I6 全部完成，Integration V1 稳定基座达成，唯一可选阶段 I6 也已启动并完成。**

---

## 3. I0–I6 逐里程碑交付核对照

### I0 — Full Corpus Gate + Integration Contract（KE commit `51d2e76`）

| Gate（主计划 §20） | 结果 |
|---|---|
| Full Corpus Index PASS | ✅ 189 篇终版 / 8828 sections / 9780 chunks，Failed 0，排除 6970 全留档（ADR-013 v2 仅终版，用户决策） |
| 一致性四方相等 | ✅ chunks=fts_terms=fts_trigram=qdrant_points=9780 |
| 人工抽样 ≥50 | ✅ 100/100 PASS（seed 20260829 可复现） |
| Full Corpus Golden Regression | ✅ Hit@5 **0.920** / MRR **0.765** / NDCG **0.801** / Exact 1.00 / Semantic 1.00 |
| Integration Contract V1 | ✅ `INTEGRATION_CONTRACT.md` |
| EvidenceReference V1 | ✅ 契约 §3（Identity + Snapshot） |
| documents/{id}/chunks + 测试 | ✅ 端点 + 契约测试 |
| Health / Error Model | ✅ index_generation + gpu_worker + 503 错误语义 |
| KE pytest 基线不下降 | ✅ **114 passed**（102 基线只增不减） |
| READINESS / FULL_CORPUS_REPORT | ✅ 两文档均产出 |

### I1 — Cognition Retrieval Proxy（cognition-app `0a950f1`）

- 仅 Node Retrieval Proxy（`server/retrieval/{client,routes,schemas,health,errors}.js`），**未改既有路由**、未动 KE；One-Writer 遵守。
- Fallback 矩阵（实测）：UNAVAILABLE / TIMEOUT / BAD_RESPONSE → legacy 子串降级（带 provider/fallback_used/fallback_reason 标记）；**空结果不降级**；400/404 不降级。
- 挂载顺序修正：`/api/retrieval/*` 必须先于 v1/v2 通用对象路由（`:type/:id` 截获问题）。
- 回归：Cognition unit 59/59、E2E 15/0、KE 114、黑盒 10/10。

### I2 — Reports Search Integration（cognition-app `b2e60f6`）

- 只替换 Reports 主搜索能力（主计划 §25），未重写页面；I3 能力未混入。
- 检索 UI：智能/精确/语义三模式（用户级 mode，内部映射 hybrid_rerank/lexical/dense）；结果卡片 Rank/Title/Heading Path/Snippet/Evidence Level/Content Type。
- 查看上下文（模态：chunk_id/行号/heading path/正文，走 `/chunks/:id`）、打开原件（POST 透传，白名单在 KE 侧）。
- 降级 UI：legacy_substring 时黄条提示，空结果与降级分离；库内浏览/阅读登记/研究结算保留。
- **GUI 冒烟七项全 PASS**（真机浏览器）：智能（HBM4→M05 Top1 0.995 级）/ 精确（CoWoS-L→M04）/ 语义（能源约束）/ 上下文模态 / 打开原件 / 阅读记录 / Legacy 降级。

### I3 — Evidence Bridge（cognition-app `7828306`）

- I3A 证据持久化：EvidenceReference V1（Identity：source_type/document_id/section_id/chunk_id/start_line/end_line/content_hash）+ Snapshot（title/heading_path/excerpt），Markdown 唯一事实源；trace 字段不落盘。
- I3B 证据→提案：`POST /api/retrieval/propose`（多证据一提案），role→add_supporting/counter_evidence，origin_type=retrieval；**零新建审批系统**，全部走既有 Proposal 预览/确认流程（不绕过 Proposal Gate）。
- I3C 前端：报告结果卡「＋支持证据/＋反方证据」→ 证据篮 → 生成提案；候选中心显示证据引用 + 「核验是否过期」（stale=hash 比对，⚠ 提示不自动覆盖）。
- **Gate 八项全 PASS**：证据持久化 / 多证据 / 预览 / Apply / Reject / Defer / 历史 trace / Stale 检测；真机测试提案均已 reject 留痕，零正式认知写入。

### I4 — Unified Runtime（整合工作区入 git）

- 交付 `D:\AI知识整合体系\runtime\{start,stop,health,common}.ps1` + pids.json + README；**两 Core 零改动**。
- start：Docker Desktop（自动拉起 180s）→ Qdrant → KE(:8765 复用真实 .venv uvicorn，等 health ≤330s) → Cognition(复用真实 start.bat，等 :3220 ≤240s) → 浏览器；幂等；-NoBrowser / -Config。
- stop：按 pids.json PID 停进程树（`/T /F`，PID 作用域，**无** `taskkill /IM`）；记录过期按端口+命令行特征发现，**不误杀无关进程**；默认保留 Qdrant。
- health：Docker/Qdrant/KE(:8765)/Cognition(:3220) 逐项 PASS/WARN/FAIL + OVERALL；退出码 0=PASS/WARN、1=FAIL。
- **Gate 实测**：冷启动一键拉起 ✅ / Docker 未启动自动拉起 ✅ / stop 干净不误杀 ✅ / health 三态 ✅（含杀服务→FAIL、CPU 降级→WARN）/ GPU→CPU 降级演练 ✅（dense 可用，hybrid 走降级）/ 回归不下降 ✅。

### I5 — Backup / Restore / Hardening（Window E）

- I5A Backup：Tier1 认知 Markdown 全量（逐文件 sha256 manifest，独立 VerifyOnly/VerifyAfter）→ 147-150 文件/≈185KB；Tier2 版本化资产（含 golden_queries.jsonl 补入 git）；Tier3 重建命令记录（manifest.rebuild）；Tier4 可选 Qdrant Snapshot。
- I5B Restore Drill（真实演练，未触碰真实认知目录）：备份→隔离副本→删 3 对象→restore→独立 sha256 全量比对 **133 一致 / 0 缺失 / 0 不符**；副本重建派生索引 38/38。
- I5C Offline Test：全链路本地化；停 Qdrant 时 KE degraded 存活、**lexical 纯 FTS 可用**、hybrid 明确 503（不静默空结果）、Cognition 自动 legacy_substring 降级；恢复后全栈 PASS。
- **I5 Gate 六项全 PASS**；回归 KE 114、cognition 64/64、E2E 15/0、黑盒 10/10、Golden 复验一致。

### I6 — Cognition Read-only Semantic Search（可选，Window F）

- **I6A KE 侧**（`aa1ae4a`）：独立 collection **`kb_cognition_chunks_v1`** + 独立 SQLite catalog，与报告 `kb_chunks_full_v1` **物理隔离**；`backend/app/cognition/{scanner,pipeline}.py` 只读 ingest 管线（复用 parser/chunker/embedding，**零写路径**）；scanner 白名单默认索引 Question/Judgment/Topic/Project/Reading Record/Review，**排除** Pending Proposal/Inbox/Rejected Candidate；`/api/search/cognition`（结果带 `scope=cognition`，READ ONLY）；health 纳入新 collection；运维脚本 `cognition_reindex.py`。
- **I6B Cognition 侧**（`6ef655b`）：复用 I1 Proxy 模式新增 `/api/retrieval/cognition-search`；`validateCognitionSearchResponse` 强制 scope 标识；cognition 降级走本地对象子串搜索；fallback 沿用 I1（404 特判 COGNITION_DISABLED）。
- **Gate 六项全 PASS**：隔离 ✅ / 索引排除 ✅（scanner 4/4）/ READ ONLY ✅ / 语义检索可用 ✅ / 回归不下降 ✅ / health 纳入 ✅。
- 端到端实测：KE hybrid `scope=cognition` count=3；Proxy `provider=knowledge_engine fallback_used=false` count=3；health「KE cognition」collection docs=37 points=142。
- 可选加分项「统一 Search Scope UI」未实施（可选非必需），前端 API `retrievalCognitionSearch` 已就绪。

---

## 4. 回归基线与质量指标对照（主计划 §57 / §58）

### 4.1 回归基线

| 项目 | 计划基线（§57） | 整合后实测 | 结论 |
|---|---|---|---|
| KE pytest | 102 passed | **114 passed**（dev 配置） | ✅ 不下降且提升 |
| Cognition unit/integration | 41/41 | **71/71**（I6 后） | ✅ 不下降 |
| Cognition E2E | 17/17 | **15/0**（脚本口径 15 项，全过无回归） | ✅ |
| Cognition 黑盒 | — | **10/10** | ✅ |
| Vite build / start.bat | PASS | PASS | ✅ |

> 注：E2E 脚本当前为 15 项检查，历史文档口径为 17 项（差异缘自脚本清理，全项通过、无回归，见 Known Issue #2）。

### 4.2 Retrieval Quality Baseline（主计划 §58）

| 指标 | 阈值（最低保持） | I0 全库实测 | I4/I5 复验 | 结论 |
|---|---|---|---|---|
| Hit@5 | ≥ 0.90 | 0.920 | 0.920 | ✅ |
| MRR | ≥ 0.75 | 0.765 | 0.765 | ✅ |
| NDCG | ≥ 0.80 | 0.801 | 0.801 | ✅ |
| Exact Hit@5 | — | 1.00 | 1.00 | ✅ |
| Semantic Hit@5 | — | 1.00 | 1.00 | ✅ |

> 已知弱项（不阻塞 Integration，§58）：causal Hit@5、cross-document MRR 相对较弱。整合过程**未借机无 A/B 调参**。

---

## 5. Definition of Done：Integration V1 逐项核对（主计划 §62）

| Done 项 | 状态 | 载体 / 证据 |
|---|---|---|
| Full Corpus Index PASS | ✅ | I0 Gate（189 篇/9780 chunks，四方一致） |
| Full Corpus Golden Regression PASS | ✅ | §4.2（0.920/0.765/0.801） |
| Integration Contract V1 | ✅ | `INTEGRATION_CONTRACT.md` |
| EvidenceReference V1 | ✅ | 契约 §3 |
| documents/{id}/chunks API 补齐 | ✅ | I0（原本地编 infra） |
| Node Retrieval Proxy | ✅ | I1 |
| Legacy Search Fallback | ✅ | I1/I2（降级矩阵 + 黄条 UI） |
| Vue Reports Hybrid Search | ✅ | I2 |
| Open Original | ✅ | I2（白名单在 KE 侧） |
| Context View | ✅ | I2（模态 + 行号） |
| Reading Record | ✅ | I2（保留既有） |
| Add to Project | ✅ | I2（保留既有） |
| Evidence → Proposal | ✅ | I3 |
| Proposal Preview / Apply | ✅ | I3 |
| Stale Evidence Detection | ✅ | I3（hash 比对，不自动覆盖） |
| Unified Start | ✅ | I4（start.ps1 一键拉起） |
| Unified Health | ✅ | I4/I6（health.ps1，含 cognition collection） |
| Backup / Restore | ✅ | I5（Tier1 manifest + Restore Drill） |
| Offline Test | ✅ | I5C |
| Retrieval Regression PASS | ✅ | §4.1 |
| Cognition Regression PASS | ✅ | §4.1 |
| Cognition E2E PASS | ✅ | §4.1 |

**Def-of-Done 22 项全部满足。**

### §63 "不接受的完成标准" —— 三项硬证明

| 要求 | 证明 |
|---|---|
| 服务失败可降级 | I1 黑盒注入 timeout/unavailable/bad schema/400 各分支；I4 CPU 降级演练；I5 停 Qdrant → dense 503、lexical 可用、Cognition 自动降级；I6 404→COGNITION_DISABLED 降级 |
| 证据可追溯 | EvidenceReference Identity 全字段 + Snapshot + content_hash，检索 trace 不落盘、不被混淆为正式认知 |
| 不会绕过 Proposal | Proposal Gate 为唯一写入通道；I3 全部测试提案经确认流程并 reject 留痕，零正式认知写入 |

---

## 6. 硬约束遵守核对照（主计划 §6 / §7 / §52 等）

| 约束 | 状态 | 说明 |
|---|---|---|
| 双库禁止合并 | ✅ | KE(catalog_full.db + qdrant) 与 Cognition(Markdown 唯一本体) 独立；I6 新增 cognition collection 亦独立于报告 collection |
| KE 对认知 READ ONLY | ✅ | I6 端点无任何写路径；检索/索引不触发认知写入 |
| 认知数据不在 git | ✅ | Tier1 由 backup.ps1 负责；I6 索引为只读消费 |
| 一律用 fixture/temp 测试认知写入（§59） | ✅ | I3/I5/I6 测试均用 fixture/隔离副本/临时 collection，未见正式认知写入 |
| 真实 Cognition 启动规范（§60） | ✅ | runtime 复用真实 `start.bat`，不复制逻辑 |
| Proposal/Evidence 安全边界（§61） | ✅ | 未来即使接入 LLM，仍走 Evidence→Proposal→Preview→Human Confirmation；禁止 LLM 直接覆盖 Judgment |
| 不重写技术栈（§52） | ✅ | 复用 KE parser/chunker/embedding；I6 未改技术栈 |
| One-Writer | ✅ | 各窗口只写其各自 Core 新增模块；既有模块改动均登记（如 runtime 属 I4/I5 资产） |
| ROCm torch 锁定 | ✅ | torch 2.9.1+rocm7.13.0，ADR-002 |

---

## 7. 已知问题 / 遗留风险（透明披露）

以下为**已发现并规避/记录**的问题，均不影响 Integration V1 稳定交付：

1. **(Known #14)** prod 配置下 KE pytest 111 passed + 3 failed，为 M5/M6 时代集成测试按 dev 样例语料断言、对生产全量语料不再成立（非本阶段回归）；dev 配置 114 passed；Golden 不受影响。建议后续改为语料无关断言。
2. **(Known #15)** CPU 降级下检索性能慢（dense ~47s、hybrid+rerank >180s），认知层 5s 代理超时会对 hybrid 走 legacy fallback——属设计内降级，非缺陷。
3. **(Known #19)** Qdrant 中断后 KE 进程内连接残留，恢复后需重启 KE 重建连接池（I5 SOP 已注明）。
4. **(Known #22)** I6 cognition catalog 的 FTS 对中文短词召回弱（lexical「就业」0 命中、dense 正常）；认知内容量小，以 dense 语义为主，属预期。
5. **(Known #23)** I6「统一 Search Scope UI」为可选加分项，未实施；API 已就绪。
6. E2E 脚本口径 15 项（历史 17 项），全过无回归，见 §4.1 注。
7. 遗留的候选内容（思维增量/负知识）默认不索引（ADR-013 v2 与主计划 §49：I6 不索引 Pending Proposal/Inbox/Rejected Candidate），后续如需检索候选，按 §50 单独 scope 并明显标识。

---

## 8. 审核员本机复现命令

> 先确认全栈已启动（`start.ps1`）；全程串行（GPU 任务与测试严禁并发，I0 资源纪律）。

```powershell
# 0) 全栈健康（应 OVERALL PASS，含 KE cognition）
cd D:\AI知识整合体系\runtime
powershell -ExecutionPolicy Bypass -File health.ps1

# 1) KE pytest（dev 配置，应 114 passed）
cd D:\AI-Knowledge-Engine
$env:KE_CONFIG='D:\AI-Knowledge-Engine\config\config.dev.yaml'
.\.venv\Scripts\python.exe -m pytest backend/tests -q

# 2) Cognition unit（应 71/71）
cd E:\CODEX\AI深度研究\cognition-app
& 'D:\AI-Knowledge-Engine\.tools\node\node.exe' --test 'tests/*.test.js'

# 3) KE cognition 语义检索（应 scope=cognition 且 count>0）
$q = @{ query='AI'; mode='hybrid'; top_k=3; options=@{ mode='hybrid'; top_k=3; rerank=$true; debug=$false } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8765/api/search/cognition' -ContentType 'application/json' -Body $q -TimeoutSec 120

# 4) Proxy cognition-search（应 provider=knowledge_engine fallback_used=false）
$p = @{ query='AI'; mode='smart'; top_k=3 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:3220/api/retrieval/cognition-search' -ContentType 'application/json' -Body $p -TimeoutSec 120

# 5) Golden Regression（prod 索引，阈值 0.90/0.75/0.80）
cd D:\AI-Knowledge-Engine
.\.venv\Scripts\python.exe backend/scripts/full_corpus_regression.py
```

---

## 9. 交付物与 commit 索引（供追溯）

| 资产 | 位置 / Commit |
|---|---|
| Integration 事实源 / 契约 | `D:\AI知识整合体系\docs\{IMPLEMENTATION_STATUS.md, INTEGRATION_CONTRACT.md, INTEGRATION_READINESS.md, PROJECT_HANDOFF_COMPENDIUM.md}` |
| Full Corpus 报告 | `D:\AI-Knowledge-Engine\docs\FULL_CORPUS_REPORT.md` |
| KE（I0） | `D:\AI-Knowledge-Engine` @ `51d2e76` |
| KE（I6A + 镜像） | @ `aa1ae4a`、`5a4b480` |
| cognition-app（I1/I2/I3） | @ `0a950f1`、`b2e60f6`、`7828306` |
| cognition-app（I6B） | @ `6ef655b` |
| Unified Runtime / Backup | `D:\AI知识整合体系\runtime\{start,stop,health,backup,restore}.ps1` |
| 整合工作区 git | @ `4826253`、`abc5c41`（I6 收尾） |
| I0-I6 契约归档 | `D:\AI-Knowledge-Engine\docs\HANDOFF_I{0,1,4,5,6}_DONE.md` |