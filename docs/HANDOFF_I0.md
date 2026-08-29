# I0 交接契约：Full Corpus Gate + Integration Contract

> 交接日期：2026-08-29 ｜ 交接方：AI-Knowledge-Engine 后端窗口（M0-M11 完成）
> 依据：`D:\AI知识整合体系\docs\AI研究知识体系整合_开发实施方案_V1.0.md`（主计划，必读）
> 开始前先读：`docs/HANDOFF_PROTOCOL.md`、主计划 §54-55（必读资料与首轮只读流程）
> 本契约覆盖 I0 全部工作；I0 期间**禁止修改 Cognition App**（主计划 §20）

---

## 0. 已核实的资产状态（交接方实测，节省新窗口侦察时间）

| 资产 | 状态 |
|---|---|
| `D:\AI-Knowledge-Engine` | git repo（主分支），pytest 102 passed 基线，最后 commit 见 git log |
| `E:\CODEX\AI深度研究\cognition-app` | **目录与代码存在（含 start.bat），但不是 git 仓库（无 .git）** —— 方案 §4 的双仓库假设在此不成立，属 §65 就绪性风险 |
| `D:\AI知识整合体系\docs\` | 已存在：实施方案 V1.0、项目整合评估资料_V0.2.md、ADR-V0.2.md、schema-v2.md、api.md 等 |
| `D:\AI知识整合体系\runtime|config|logs` | 尚不存在（I4 才需要） |
| `D:\AI深度报告归档` | 真实知识源（数千文件），只读 |
| KE 当前索引 | dev 语料：10 篇 / 725 chunks（`data/catalog.db` + kb_chunks_v1/v2 collections）；config.yaml roots 指向 `data/dev_kb` |

### 就绪性风险处置建议（写入 INTEGRATION_READINESS.md）

1. **cognition-app 无 git**：首次修改前先 `git init` + 初始 commit（保留原始状态快照），
   再建 `integration/research-os-v1` 分支； KE repo 同样建该分支。
2. **catalog 策略**：全量索引建议使用独立 catalog（如 `data/catalog_full.db`）或明确
   决定重建 `data/catalog.db`；注意 test_api 依赖 dev seed 状态（见 §4.3）。

---

## 1. I0 任务范围（主计划 §10-20）

按顺序执行，全部完成后才允许进入 I1：

### 1.1 Full Corpus Index（对真实归档全量索引）

1. 切换索引目标：KE `config.yaml` 的 `knowledge_base.roots` → `D:/AI深度报告归档`
   （config.example.yaml 保留原值；dev seed 的 roots 配置留档）；
2. 用 `backend/scripts/reindex.py scan` 执行全量索引（内部走 GPU worker；
   吞吐参考：GPU ~16ms/chunk，数千文件预计 1-3 小时，属正常）；
3. 生成 `docs/FULL_CORPUS_REPORT.md` + `data/full_corpus_stats.json` +
   `data/full_corpus_failures.json`，统计项见主计划 §11（Total Files/Parsed/
   Skipped/Failed/Sections/Chunks/FTS×2/Qdrant Points/Duplicate IDs/Encoding
   Failures/Parser Warnings/Oversized Chunks）。

### 1.2 一致性 Gate（主计划 §12）

`chunks = fts_terms = fts_trigram = qdrant_points`（有排除必须输出 Exclusion Reason
+ Count，禁止静默不一致）。现有工具：`backend/scripts/reindex.py check`
（per-document 四方计数）。

### 1.3 全库人工抽样（主计划 §13）

随机抽 ≥50 篇（推荐 100），核对 metadata/heading tree/line range/tables/formula/
reference/audit/encoding。输出抽样清单与结论（可生成脚本 + 人工核对记录）。

### 1.4 全库 Golden Regression（主计划 §14）

在**全量索引**上重跑 50 条 Golden Query（Hit@5/MRR/NDCG/Exact/Semantic）。
注意：现有 `backend/scripts/m9_eval.py` 会从 fixtures 自建临时语料——I0 需要一个
指向**生产 catalog/Qdrant** 的回归脚本（如 `backend/scripts/full_corpus_regression.py`，
复用 m9_eval 的 resolve/metrics 逻辑）。Gate：Hit@5≥0.90 / MRR≥0.75 / NDCG≥0.80。

### 1.5 补齐 Retrieval API（主计划 §18）

- `GET /api/documents/{id}/chunks`（列表端点，替代前端 deterministic 枚举规避方案）；
- 稳定 `GET /api/chunks/{id}`、`GET /api/documents/{id}`、`GET /api/documents/{id}/sections`、
  `GET /api/health`（已存在，补测试固化契约）。

### 1.6 Health / Error Model（主计划 §19）

- `/api/health` 增加 `index_generation`（catalog schema_version + chunker/lexical
  version，来自 meta 表）与 gpu_worker 明细（现已在 /api/index/status，聚合进来）；
- 错误码语义对齐：服务故障必须返回错误体（AppError 体系），**禁止伪装成空结果**；
  Cognition 侧的 RETRIEVAL_UNAVAILABLE/TIMEOUT/BAD_RESPONSE/EVIDENCE_STALE 等映射
  写入 INTEGRATION_CONTRACT.md。

### 1.7 Integration Contract V1 + EvidenceReference V1（主计划 §15-17）

写入 `D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md`：
- Search API 契约（POST /api/search，request/response 形态，含 EvidenceReference）；
- **EvidenceReference V1 schema**：Identity = source_type/document_id/section_id/
  chunk_id/content_hash/start_line/end_line（主计划 §16）；reranker_score 等
  trace 字段不得作为持久 Identity；
- Health/Error Model、稳定性承诺（pytest 102 基线 + Golden Gate 阈值）。

---

## 2. I0 Gate（主计划 §20，全部满足才能进 I1）

```text
[ ] Full Corpus Index PASS（一致性四方相等 + 抽样通过）
[ ] Full Corpus Golden Regression PASS（Hit@5>=0.90 / MRR>=0.75 / NDCG>=0.80）
[ ] Parser Fatal Rate <= 0.5%，No Silent Data Loss
[ ] Integration Contract V1 完成（INTEGRATION_CONTRACT.md）
[ ] EvidenceReference V1 完成
[ ] documents/{id}/chunks 端点 + 测试完成
[ ] Health / Error Model 完成
[ ] KE pytest 基线不下降（102 passed 只增不减）
[ ] INTEGRATION_READINESS.md / FULL_CORPUS_REPORT.md 产出齐全
```

---

## 3. KE 代码库工程要点（交接方实测，直接可用）

- **全量索引入口**：`backend/scripts/reindex.py scan`（内部 staging→事务→Qdrant，
  失败自动记录 errors）；监控：`reindex.py check`；
- **测试基线**：102 passed。注意 `test_api.py` 依赖 dev seed catalog（等待
  documents>=10、依赖 M04/M07 存在）——切换 roots 后 startup reconcile 会对全库
  触发索引！**I0 必须解耦**：test_api 改用独立 tmp 语料 fixture（参照
  test_indexing.py 的 env fixture 模式，roots 指向 tmp），否则跑测试会误索引全库；
- **GPU worker**：/api/search 经 InferenceManager；全量索引用 `reindex.py scan`
  （同样走 worker）；worker 连续崩溃 2 次自动 CPU fallback（全量索引时留意日志）；
- **sections 向量**：`index_file` 只重建 chunks 向量；sections 向量由
  `dense.index_sections` 单独负责（M10 seed 曾因此漏掉，见 Known Issues）——
  全量索引管线需包含 sections（复用 `build_section_records`）；
- **Raw report 编码**：parser 假定 UTF-8；全量语料可能出现非 UTF-8 文件
  （pipeline 已捕获 UnicodeDecodeError → SourceFileError，计入 Failed Files 即可）；
- **根目录噪音**：归档内含 zip/html/旧镜像目录；scanner 只取
  `cfg.knowledge_base.extensions`（.md）且跳过 `~$` 前缀——统计 Skipped 时以此为据；
- **Golden 标注兼容性**：50 条标注用 heading_contains 锚定（ADR-012），
  全量语料中同源文档的 section 应能同样解析；若个别查询在全库中出现
  "多个报告含同名 section" 导致 Recall 语义变化，属预期，如实记录即可。

---

## 4. 交付格式（主计划 §64）

每步输出：Code Changes / Files Modified / Commands Run / Tests Run / Test Results /
Evaluation / Known Issues / ADR Changes / Git Commit / Next Milestone。

Git：KE 与 cognition-app 保持独立 repo；建 `integration/research-os-v1` 分支；
集成文档写 `D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md`（整合事实源），
KE 的 IMPLEMENTATION_STATUS.md 同步登记 I0 状态。

---

## 5. 完成后

按 `HANDOFF_PROTOCOL.md` 结束流程收尾：更新两个 IMPLEMENTATION_STATUS、
归档本契约（HANDOFF_I0_DONE.md）、编写 I1（Cognition Retrieval Proxy）交接契约
——I1 开始才允许修改 cognition-app（先 git init，见 §0）。
