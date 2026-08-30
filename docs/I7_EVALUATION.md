# I7 Post-Integration Stabilization 评估报告

> as-of：2026-08-30 ｜ 范围：仅 I7 稳定化（未进入 LLM/MCP/Agent）｜ 依据：外部审计任务书
> 基座：M0–M11、I0–I6 全部完成，Integration V1 Stable。

## 1. Baseline（Task 0，开始前记录）

| 仓库 | 分支 | 开始 commit | dirty |
|---|---|---|---|
| KE | integration/research-os-v1 | `5a4b480` | 干净 |
| cognition-app | integration/research-os-v1 | `6ef655b` | `.trae_write_test.txt`（已知写入测试残留，E盘权限无法删除，非代码） |
| Integration workspace | main | `d4c7cce` | 干净 |

全栈 health PASS；KE docs=189、cognition docs=37/points=142；回归：KE pytest dev 114 / prod 111+3 failed、cognition unit 71/71、E2E 15/0、黑盒 10/10；Golden 0.920/0.765/0.801。

## 2. Files Changed

- **KE**：`conftest.py`、`test_dense_index.py`、`test_search_engine.py`（P0-1）；`qdrant.py`、`dense.py`、`test_qdrant_recovery.py`（P0-2）；`main.py`、`test_cognition_ingest.py`（P0-3）；`cognition_golden_eval.py` + 数据（P0-4）；`exclusion_audit.py` + 数据（P1-3）；新文档 ×3。
- **cognition-app**：`scripts/e2e.js`（P1-2 注释）；`frontend/src/views/ReportsView.vue` + dist（P1-1）。

## 3. Repo / Commit Matrix

| 阶段 | KE | cognition-app |
|---|---|---|
| P0-1 Test Isolation | `f5c0fd3` | — |
| P0-2 Qdrant Recovery | `92cbebc` | — |
| P0-3 Cognition Incremental | `b4a1f50` | — |
| P0-4 Cognition Golden | `25d66c0` | — |
| P1-3 Exclusion Audit | `ea166c5` | — |
| P1-2 E2E Baseline | — | `debfd6c` |
| P1-1 Search Scope UI | — | `4882952` |
| **收尾**（本批次） | I7 三文档 + 实现 |

## 4. Test Isolation（P0-1）→ PASS

- 独立 fixture collection `kb_chunks_fixtest`/`kb_sections_fixtest` + 独立 SQLite（conftest `fixture_retrieval`，基于 10 篇 fixtures），与 dev/prod 生产库完全解耦。
- dev 配置：完整 pytest 全绿；**prod 完整 pytest 全绿（原 111+3 failed → 0 failed）**；原 3 个失败测试（`test_exact_query_top`/`test_semantic_rewrite_queries`/`test_search_modes`）改为 fixture 确定性断言。
- Golden Evaluation 独立保留真实语料测试（`cognition_golden_eval.py`/`full_corpus_regression.py`）。
- 未通过"改生产预期/降断言/忽略失败"解决。

## 5. Qdrant Automatic Recovery（P0-2）→ PASS（真机故障注入）

- 机制：`QdrantStore` client 失效标记 + 懒重建（`@property`）+ `recover()`；`dense.search/_upsert/delete` 失败后 `mark_invalid→recover→原地重试一次`；`health()` 单次快探活。
- 实测：**ON→hybrid OK**；**OFF→health degraded + hybrid 503 + lexical 可用 + Cognition legacy_substring 降级**；**ON again→未重启 KE，Dense/Hybrid 自动恢复（count=3）+ health 回 ok**。
- 单测 `test_qdrant_recovery.py` 3/3；回归 pytest 全绿。

## 6. Cognition Incremental Sync（P0-3）→ PASS

- I6 已具备 scanner 六态 + pipeline 原子替换/删除级联；补齐：**独立 Cognition watcher**（用 `cognition.periodic_reconcile_seconds`=300 可配置，解耦报告 watcher），restart reconcile 沿用 startup。
- 测试强化：`test_modify_and_delete_incremental` 新增 **no orphan Qdrant point**（modify 新词可检索、delete 后被删文档 qdrant 点清除、points==catalog chunks）与 no orphan catalog row；READ ONLY 断言保留。
- 8/8 全绿。NEW/MODIFY/DELETE/periodic/restart/READ-ONLY 全验证。

## 7. Cognition Golden Metrics（P0-4）→ PASS

见 `COGNITION_GOLDEN_EVALUATION.md`：**Hit@5=1.000、MRR@10=0.853、NDCG@10=0.788**（25 条人工标注，全类型 Hit@5=1.0）。Project 类型因真实语料无对象不可标注（已披露）。据此确认**无需为检索质量重修 Cognition FTS**。

## 8. Search Scope UI（P1-1）→ PASS

- ReportsView 增加「全部 / 研究资料 / 我的认知」三档 Scope。
- 「全部」并行调 Reports(cognition search) 与 Cognition(cognition-search)，**分组显示、不跨库原始分数融合**；「研究资料」「我的认知」单 scope。
- Vite build 通过。

## 9. E2E Canonical Baseline（P1-2）

- 规范为 **E2E v1.0 · 15 tests**（e2e.js 顶部标注，历史 17 项口径废弃）。
- 后续 IMPLEMENTATION_STATUS / handoff 统一采用此口径。

## 10. Exclusion Audit（P1-3）→ PASS

见 `EXCLUSION_AUDIT.md`：DIR 92.4%/NON_FINAL 4.9%/PROCESS 2.8%/DUP 27；抽查全为旧版本/重复/非终版/中间产物，**无系统性误排除**。ADR-013 v2 不变。

## 11. Regression

- KE：dev 完整 pytest 全绿；prod 完整 pytest 全绿。
- cognition-app：unit 71/71（未受影响），Search Scope UI build 通过。
- 全栈 health OVERALL PASS（含 cognition）。

## 12. Known Issues（新增/保留）

- I7-1 Project 类型无正式认知对象，Cognition Golden 无法标注该类型覆盖（真实数据缺失）。
- I7-2 Cognition FTS 中文短词 weak（「就业」lexical 0 命中）——Golden 证明 dense/hybrid 已满足真实检索，本轮不修（任务书 §7）。
- I7-3 `.trae_write_test.txt` 残留（E盘权限）不纳入版本控制。
- 保留 I0-I5 Known #14-#24，其中 **#14（prod 3 failed）已由 P0-1 根治**。

## 13. ADR Changes

- 本轮未改检索排名（RRF/embedding/reranker/chunker 均未动），未产生新 ADR。P0-2 增强了运行期容错（非排序语义变化）；P0-1 仅为测试隔离。

## 14. Final Gate Checklist

```
[x] KE tests corpus-independent
[x] dev deterministic tests clean
[x] prod deterministic tests clean
[x] Qdrant OFF degradation PASS / ON auto-recovery PASS / no restart
[x] Cognition incremental NEW/MODIFY/DELETE PASS / periodic reconcile PASS / no orphan
[x] Cognition Golden Set 25（>=20）；Hit@5=1.000>=0.90；MRR=0.853>=0.75；per-type 可用
[x] Unified Search Scope UI PASS（分组显示、不跨库融分）
[x] E2E canonical baseline 统一（v1.0 · 15 tests）
[x] Exclusion reason report 完成；抽样>50；无系统性误排除
[x] Report Golden 不变 / Cognition 回归不变 / Proposal Gate 不变 / READ ONLY 不变
```

## 15. Recommended Next Stage

按任务书 §20：完成后 **STOP，不自动进入 LLM/MCP/Agent**。候选下一阶段（须单独规划 + 用户重新评估）：
**Evidence-grounded LLM Synthesis Pilot**（沿 Evidence→Proposal→Human Confirmation 链，禁止 LLM 直接覆盖 Judgment）。