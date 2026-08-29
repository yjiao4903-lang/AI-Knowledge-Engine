# I1 交接契约：Cognition Retrieval Proxy

> 交接日期：2026-08-30 ｜ 交接方：I0 整合窗口
> 前置：I0 已完成（docs/HANDOFF_I0_DONE.md，Gate 全 PASS）
> 依据：主计划 §21-24、§57（Cognition 基线不得下降）

## 0. 接手前必读

1. `D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md`（Search API / EvidenceReference /
   Health / Error Model 契约——Proxy 是该契约的 Node 侧实现）；
2. `D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md`（整合事实源）；
3. `D:\AI-Knowledge-Engine\docs\FULL_CORPUS_REPORT.md`（全量语料状态）。

## 1. 首步（未做不可写代码）

```text
cd E:\CODEX\AI深度研究\cognition-app
git init && git add -A && git commit -m "baseline: V0.2 原始状态（I1 前）"
git checkout -b integration/research-os-v1
```

cognition-app 实测无 git（HANDOFF_I0 §0）；修改前必须先快照原始状态。
真实项目唯一，评估资料副本（D:\AI知识整合体系\docs\项目整合评估资料_V0.2.md）只读。

## 2. 任务范围（主计划 §21-24）

新增 `server/retrieval/`（client.js / routes.js / health.js / errors.js）：

- Proxy API：`POST /api/retrieval/search`、`GET /api/retrieval/health`、
  `GET /api/retrieval/documents/:id`、`GET /api/retrieval/chunks/:id`
  （可加 `/documents/:id/chunks`、`/documents/:id/sections`，按 I2 UI 需要定）；
- Node 只做：转发 / timeout / error mapping / schema validation / fallback；
  禁止实现 RRF、Embedding、访问 Qdrant 或 Retrieval SQLite；
- Integration Config（主计划 §23）：`retrieval.enabled / base_url(http://127.0.0.1:8765) /
  timeout_ms(5000) / fallback_legacy_search(true)`；
- 错误映射按 INTEGRATION_CONTRACT.md §4.2：
  503→RETRIEVAL_UNAVAILABLE、超时→RETRIEVAL_TIMEOUT、schema 失败→RETRIEVAL_BAD_RESPONSE
  （三者触发 legacy fallback），400→BAD_REQUEST（不 fallback），404→REPORT_NOT_FOUND。

## 3. 测试与基线（主计划 §24，任何下降都要解释）

- 新增 Proxy 测试：healthy / offline / timeout / invalid response / empty result /
  legacy fallback（用 mock KE 端口，勿依赖真机 GPU）；
- Cognition 基线：41/41 unit+integration、17/17 E2E、Vite build PASS、start.bat PASS；
- I0 期间 KE 未改 Cognition——I1 亦不得改 Cognition 认知数据（只加代码路径）。

## 4. 注意事项（I0 实测，直接可用）

- KE 生产配置已切全量：document_id 为终版报告 ID（M01-M25、主题目录名等 189 篇），
  `GET /api/documents/{id}/chunks` 已可用（I2 UI 直接用，勿再用 chunk_id 探针枚举）；
- KE 后端启动：`D:\AI-Knowledge-Engine` 下
  `.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --port 8765`
  （config.yaml 已是全量）；Qdrant 需 Docker（ai-kb-qdrant）；
- 搜索 P95 全库 ~1.4s（rerank），Node timeout_ms=5000 合理；
- KE pytest 基线 114 passed；KE 侧如需改动走 ADR + Golden A/B；
- 资源纪律：GPU 任务与测试严格串行（I0 曾并发致内存耗尽）。

## 5. 完成后

按 HANDOFF_PROTOCOL 收尾：更新两份 IMPLEMENTATION_STATUS、git checkpoint、
本契约归档为 HANDOFF_I1_DONE.md、编写 I2 契约（Reports 页面融合 + Legacy fallback GUI 验证）。

---

## 完成登记（2026-08-30，Window C / I0-I3 归档）

HANDOFF_I1.md 覆盖的 I1 已完成；随后同窗口连续完成 I2（Reports 融合）与 I3（Evidence Bridge）：
- cognition-app：`0a950f1`(I1) → `b2e60f6`(I2) → `7828306`(I3)，分支 integration/research-os-v1
- 回归基线：unit 64/64、E2E 15/0、跨系统黑盒 10/10（D:\AI知识整合体系\integration_tests\run.js）
- 详细交付记录：D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md（I1/I2/I3 交付摘要）
- 补充方案 §42 的 I1 交付要求全部满足；I2 Gate 七项 GUI 冒烟、I3 Gate 八项验证均 PASS
- 交接偏差：I1 契约 §5 要求的 I2 契约未单独成文（I2/I3 由补充方案细化路线直接承接）
