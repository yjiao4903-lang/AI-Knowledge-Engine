# Personal AI Research OS 整合项目 — 对外项目指导审核报告（I0–I7）

> **文档性质**：交付外部项目指导的完整开发进展汇总，对照主开发计划 V1.0 与 I7 外部审计任务书逐项核对。
> **as-of 日期**：2026-08-30 ｜ **覆盖范围**：M0–M11、Integration I0–I7
> **主计划基准**：`D:\AI知识整合体系\docs\AI研究知识体系整合_开发实施方案_V1.0.md`
> **唯一进度事实源**：`D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md`
> **I7 审计依据**：`Personal_AI_Research_OS_I7_Post_Integration_Stabilization_任务书.md`
>
> **可复现性声明**：本报告全部"通过/完成"结论可在本机按其标注命令复现，非"页面打开/API 200/编译通过"式宣称完成（主计划 §63）。

---

## 1. 项目定位与目标（主计划 §0 / §69）

两套系统**不合并代码库/数据库/后端**，整合为单一产品：

- **Cognition App**（Vue）= 认知控制平面，拥有**唯一正式认知写入权限**。
- **AI Knowledge Engine** = Evidence Engine（Parser/Chunker/FTS/Dense/Hybrid/Reranker/Qdrant/Search API），**对认知只读**。
- 唯一正式整合边界 = **API / EvidenceReference**；正式认知写入统一走 Cognition、经 Human Confirmation，核心链 `Report→Retrieval→Evidence→Proposal→Human Confirmation→Cognition Update` 不可破坏。

---

## 2. 开发路线完成总览（主计划 §9 / §68 + I7 任务书）

`M0–M11 → I0→I1→I2→I3→I4→I5 → Integration V1 Stable → I6 → I7 → Future`

| 阶段 | 计划目标 | 状态 | 关键 Gate |
|---|---|---|---|
| M0–M11 | 既有 Retrieval（报告引擎） | ✅ | pytest 102 → 114 |
| **I0** | Full Corpus + Integration Contract | ✅ | 全库 Gate 全 PASS |
| **I1** | Cognition Retrieval Proxy | ✅ | 回归 PASS |
| **I2** | Cognition Reports 融合 | ✅ | GUI 七项 PASS |
| **I3** | Evidence → Proposal Bridge | ✅ | Proposal Gate PASS |
| **I4** | Unified Runtime | ✅ | One-click PASS |
| **I5** | Backup / Restore / Hardening | ✅ | Restore PASS |
| **Integration V1 Stable** | I0–I5 基座 | ✅ | DoD 22 项全满足 |
| **I6** | Cognition Read-only Semantic Search（可选） | ✅ | Gate 六项 PASS |
| **I7** | Post-Integration Stabilization（外部审计） | ✅ | Final Gate 全 PASS |
| Future | LLM/MCP/Agent | ⬜ 未启动（I7 §20 要求 STOP） | — |

**结论：主计划 I0–I6 全部完成；I7 稳定化（外部审计任务书 P0×4 + P1×3）全部完成；Integration V1 稳定基座达成。按 I7 §20 已停止，未自动进入 LLM/MCP/Agent。**

---

## 3. I0–I6 逐里程碑交付（已完成，摘要）

完整逐项核对照见 `docs/PROJECT_REVIEW_REPORT_I0_I6.md`；要点：

- **I0**：189 终版/8828 sections/9780 chunks 四方一致；Golden 0.920/0.765/0.801/1.00/1.00；Contract V1 + EvidenceReference V1；pytest 114（基线 102 增）。
- **I1**：Node Retrieval Proxy；Fallback 矩阵（UNAVAILABLE/TIMEOUT/BAD_RESPONSE→legacy；空结果/400 不降级）；挂载顺序修正。
- **I2**：Reports 三模式检索 + 上下文/打开原件/降级 UI；GUI 冒烟七项 PASS。
- **I3**：EvidenceReference V1 持久化 + 证据→提案（走 Proposal Gate 不绕过）；Stale 检测；Gate 八项 PASS。
- **I4**：Runtime {start,stop,health}.ps1 一键全栈；故障演练 GPU→CPU。
- **I5**：Tier1 认知 Markdown 备份 sha256 manifest + Restore Drill 133 一致 + Offline Test；Gate 六项 PASS。
- **I6**：独立 `kb_cognition_chunks_v1`（docs=37/points=142）只读语义检索；`/api/search/cognition` + `scope=cognition`；增量 scanner/pipeline；Gate 六项 PASS。

---

## 4. I7 Post-Integration Stabilization（外部审计，2026-08-30）

### P0 成果

| P0 | 结论 | 证据 |
|---|---|---|
| **P0-1 测试语料解耦** | ✅ | M5/M6 改用独立 fixture collection+SQLite（conftest `fixture_retrieval`），与生产 dev/prod 解耦；**prod 完整 pytest 由 111+3 failed → 0 failed**（ Known #14 根治）|
| **P0-2 Qdrant 自动恢复** | ✅ | `QdrantStore` client 失效重建 + dense 原地重试；真机 ON→OFF→ON **未重启 KE 即恢复 Dense/Hybrid**、health 回 ok、lexical/降级契约正确 |
| **P0-3 Cognition 增量同步** | ✅ | 独立 cognition watcher（周期 300s 可配置）；测试补 qdrant no-orphan；NEW/MODIFY/DELETE + periodic/restart + READ ONLY 全过 |
| **P0-4 Cognition Golden** | ✅ | 25 条人工标注；**Hit@5=1.000 / MRR@10=0.853 / NDCG@10=0.788**；据此暂不修 Cognition FTS |

### P1 成果

| P1 | 结论 | 证据 |
|---|---|---|
| **P1-1 Search Scope UI** | ✅ | 报告库「全部/研究资料/我的认知」；"全部"分组显示不跨库融分；Vite build 通过 |
| **P1-2 E2E 口径** | ✅ | 统一 **E2E v1.0 · 15 tests**（deprecate 历史 17）|
| **P1-3 Exclusion Audit** | ✅ | DIR 92.4%/NON_FINAL 4.9%/PROCESS 2.8%/DUP 27；取样 50+ 无系统性误排除；ADR-013 v2 不变 |

---

## 5. 回归基线与质量指标

### 5.1 回归基线

| 项目 | 计划基线 | 当前 | 结论 |
|---|---|---|---|
| KE pytest | 102 | **dev/prod 双配置全绿**（dev ~200 / prod 0 failed）| ✅ 不下降 |
| Cognition unit | 41/41 | **71/71** | ✅ |
| Cognition E2E | — | **v1.0 · 15 tests** | ✅ 口径统一 |
| 黑盒 | — | 10/10 | ✅ |

### 5.2 Retrieval / Cognition 质量

| 指标 | 值 | 阈值 | 判定 |
|---|---|---|---|
| Report Golden Hit@5 | 0.920 | ≥0.90 | ✅ |
| Report Golden MRR@10 | 0.765 | ≥0.75 | ✅ |
| Report Golden NDCG@10 | 0.801 | ≥0.80 | ✅ |
| Cognition Golden Hit@5 | **1.000** | ≥0.90 | ✅（I7 P0-4）|
| Cognition Golden MRR@10 | **0.853** | ≥0.75 | ✅ |
| Cognition Golden NDCG@10 | 0.788 | 记录 | ✅（非 blocker）|

---

## 6. Definition of Done / 验收核对照

### Integration V1 DoD（主计划 §62）：22 项全满足（同 I0-I6 报告 §5）

### I7 Final Gate Checklist：15 项全满足（对应 I7 任务书 §16）

| Gate | 结果 |
|---|---|
| KE tests corpus-independent | ✅ |
| dev / prod deterministic tests clean | ✅ |
| Qdrant OFF degradation + ON auto-recovery + no restart | ✅ |
| Cognition incremental NEW/MODIFY/DELETE + periodic + no orphan | ✅ |
| Cognition Golden Set 25（≥20）；Hit@5≥0.90；MRR≥0.75；per-type | ✅ |
| Unified Search Scope UI + 分组显示 + 不跨库融分 | ✅ |
| E2E canonical baseline 统一 | ✅ |
| Exclusion reason 量化 + 抽样>50 + 无误排除 | ✅ |
| Report Golden / Cognition 回归 / Proposal Gate / READ ONLY 不变 | ✅ |

---

## 7. 硬约束遵守（主计划 §6/§7/§52、I7 §12）

| 约束 | 状态 |
|---|---|
| 双库禁止合并 / Report collection != Cognition collection | ✅ |
| KE 对 Cognition READ ONLY（I6 无写路径、I7 增量 sync 只扫不改）| ✅ |
| 正式认知变化必须走 Proposal（Proposal Gate 不绕过）| ✅ |
| 认知 Markdown 唯一正式事实来源；认知数据不在 git | ✅ |
| 不重写技术栈 / 不改 Retrieval ranking（I7 未调 RRF/embedding/reranker/chunker）| ✅ |
| ROCm torch 2.9.1+rocm7.13.0 锁定 | ✅ |
| GPU 任务与大规模测试串行（I0 资源纪律）| ✅ |
| Runtime 复用真实 start.bat | ✅ |

---

## 8. Known Issues（透明披露，I0–I7 汇总）

- **(I4 #14，已根治)** prod 3 failed → I7 P0-1 测试解耦后 prod 全绿（已关闭）。
- **(I4 #15)** CPU 降级检索慢 → 设计内降级，非缺陷。
- **(I5 #19)** qdrant 中断后需重启 KE → **已由 I7 P0-2 根治**（自动恢复）。
- **(I6 #22)** Cognition FTS 中文短词弱 → Golden 证明 dense/hybrid 已满足真实检索，本轮不修（I7 §7）。
- **(I6 #23)** Search Scope UI 原未实施 → **已由 I7 P1-1 实施**。
- **(I7 #25)** Project(06_研究项目) 正式语料无对象 → Cognition Golden 该类型不可标注（真实数据缺失）。
- **(I7 #27)** cognition-app `.trae_write_test.txt` 残留（E盘权限），不纳入版本控制。
- *(I0 #11/#12/#13 等历史 items 仍留档，见 IMPLEMENTATION_STATUS)*。

---

## 9. 审核员本机复现命令

> 全栈启动后使用；GPU 与测试严格串行。

```powershell
# 全栈健康
cd D:\AI知识整合体系\runtime
powershell -ExecutionPolicy Bypass -File health.ps1

# KE pytest（dev 与 prod 双配置均应全绿）
cd D:\AI-Knowledge-Engine
$env:KE_CONFIG='D:\AI-Knowledge-Engine\config\config.dev.yaml'; .\.venv\Scripts\python.exe -m pytest backend/tests -q
$env:KE_CONFIG=$null; .\.venv\Scripts\python.exe -m pytest backend/tests -q

# Qdrant 自动恢复（真机）
docker stop ai-kb-qdrant; Invoke-RestMethod http://127.0.0.1:8765/api/health  # degraded
docker start ai-kb-qdrant  # 不重启 KE，立即再检索应恢复
Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/search -ContentType application/json -Body '{"query":"HBM4","options":{"mode":"hybrid"}}'

# Cognition Golden
.\.venv\Scripts\python.exe backend/scripts/cognition_golden_eval.py   # Hit@5=1.0 MRR=0.853

# Exclusion Audit
.\.venv\Scripts\python.exe backend/scripts/exclusion_audit.py
```

---

## 10. Commit 索引（供追溯）

| 仓库 | 关键 commit |
|---|---|
| **KE** `integration/research-os-v1` | I0 `51d2e76`；I6A `aa1ae4a`；P0-1 `f5c0fd3`；P0-2 `92cbebc`；P0-3 `b4a1f50`；P0-4 `25d66c0`；P1-3 `ea166c5`；交付文档 `23cd93a`；HEAD `cf05c51` |
| **cognition-app** `integration/research-os-v1` | I1/I2/I3 `0a950f1`/`b2e60f6`/`7828306`；I6B `6ef655b`；P1-2 `debfd6c`；P1-1 `4882952`（HEAD）|
| **整合工作区** `main` | I6 `4826253`+`abc5c41`；审核报告 `d4c7cce`；I7 `8d8f64c`（HEAD）|
| I7 交付物 | `docs/I7_EVALUATION.md`、`docs/COGNITION_GOLDEN_EVALUATION.md`、`docs/EXCLUSION_AUDIT.md` 及 `data/cognition_golden_*`、`data/exclusion_audit_*` |

---

## 11. 当前状态与下一步建议

- **当前**：I0–I7 全部完成，全栈 OVERALL PASS（KE docs=189 + cognition docs=37/points=142），Integration V1 稳定 + I7 稳定化达成。**此 STOP 点由用户决定是否继续。**
- **候选下一阶段（需单独规划 + 用户/指导重新评估）**：**Evidence-grounded LLM Synthesis Pilot** —— 沿 `Evidence→Proposal→Preview→Human Confirmation` 链落地，禁止 LLM 直接覆盖 Judgment（主计划 §61 / I7 §20）。亦可在 Cognition Golden 补齐 Project 类型覆盖后再评估 FTS 优化。