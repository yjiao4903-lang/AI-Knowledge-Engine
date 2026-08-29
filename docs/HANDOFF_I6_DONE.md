# I6 交接契约：Cognition Read-only Semantic Search（Window F，可选）【已完成】

> 状态：**DONE（2026-08-30）** ｜ 交接方：Window E（I5 Lead）→ 执行方：Window F
> 依据：主计划 §48-50；I0-I5 全部完成并归档

## 完成记录（2026-08-30）

- **I6A KE 侧**：新增独立 collection **`kb_cognition_chunks_v1`** + 独立 SQLite catalog
  （`catalog_cognition.db`），与报告 `kb_chunks_full_v1` 物理隔离；
  `backend/app/cognition/{scanner,pipeline}.py` 只读 ingest 管线（复用 parser/chunker/embedding，
  零写路径）；scanner 白名单默认索引 Question/Judgment/Topic/Project/Reading Record/Review，
  排除 Pending Proposal/Inbox/Rejected Candidate；`/api/search/cognition` 端点（结果带
  `scope=cognition` 来源标识，READ ONLY 无写路径）；health 纳入新 collection 状态；
  运维脚本 `backend/scripts/cognition_reindex.py`。**KE commit：本提交（I6A）**
- **I6B Cognition 侧**：复用 I1 Proxy 模式新增 `/api/retrieval/cognition-search`
  （`server/retrieval/{routes,client,schemas}.js` + `server/index.js` 传入本地 search 供降级 +
  `frontend/src/api.js` `retrievalCognitionSearch`）；`validateCognitionSearchResponse` 强制
  scope 标识；cognition 降级走本地认知对象子串搜索（形状同 I1 legacy 卡片）；
  fallback 矩阵沿用 I1（UNAVAILABLE/TIMEOUT/BAD_RESPONSE→降级；空结果/400/404 不降级，
  404 特判 COGNITION_DISABLED）。**cognition-app commit：`6ef655b`**，unit 71/71
- **I6 Gate 全 PASS**：
  1. ✅ `kb_cognition_chunks_v1` 与报告 collection 物理隔离（独立 collection 实测，health 独立展示）
  2. ✅ 默认索引对象与排除对象正确（scanner 白名单单测 4/4，inbox/候选/归档不入清单）
  3. ✅ KE 对认知 READ ONLY（ingest/检索无写路径；Gate 阶段验证）
  4. ✅ Cognition 语义检索可用（端到端实测：KE hybrid scope=cognition count=3；
     Proxy provider=knowledge_engine fallback_used=false count=3，结果带来源标识）
  5. ✅ 回归不下降：KE pytest dev 114（Gate 阶段）、cognition-app unit **71/71**
     （64 基线 + 7 新增）、E2E 15/0、黑盒 10/10、Golden 不变
  6. ✅ Unified Health 纳入新 collection（health.ps1「KE cognition」PASS，docs=37 points=142）
- **已知问题**：
  - I6.1 cognition catalog 的 FTS（terms/trigram）对中文短词召回弱（如「就业」lexical 0 命中，
    dense 正常）；hybrid 融合可用，认知检索以 dense 语义为主——非缺陷，认知内容量小属预期。
  - I6.2 可选加分项「统一 Search Scope（全部/研究报告/我的正式认知）」UI 未实施（可选非必需）；
    前端已具备 `retrievalCognitionSearch` API，后续接入口即可。
  - I6.3 认知数据不在 git（硬约束），索引为只读消费；cognition collection 属 Tier3 可重建
    （`cognition_reindex.py`），不在 Tier1 备份范围（I5 manifest.rebuild 已记录）。

## 硬约束

- 双库禁止合并；Retrieval 对认知只读；Proposal Gate 不可绕过；不重写技术栈；
- ROCm 锁定 torch 2.9.1+rocm7.13.0；GPU 任务与测试严格串行（I0 事故教训）；
- 认知数据不在 git——I6 索引为只读消费，任何写操作须先 ADR 并经负责人批准；
- One-Writer：I6 窗口只写 KE 新增模块 + cognition 只读代理；改既有模块先在本契约登记理由。
