# 项目总体评估报告（供外部窗口评估）

> 生成日期：2026-08-29 ｜ 生成方：后端主窗口（M0-M10）+ 前端窗口（M11）
> 依据：开发规格书 v1.0（含三份 Addendum）、docs/IMPLEMENTATION_STATUS.md（唯一事实源）
> 评估基线 commit：`9a4f90a`（M11 完成）

---

## 1. 项目定位

本地单机研究知识检索系统（非 RAG Demo）：对 `D:\AI深度报告归档` 的高密度中文
Markdown 研究报告建立 **结构化解析 → 语义分块 → 三路检索（Dense + Terms BM25 +
Trigram）→ Weighted RRF 融合 → Reranker 重排** 的可解释检索基础设施，
React 前端提供搜索/文档查看/索引管理。

## 2. 里程碑完成矩阵（M0-M11 全部交付）

| 里程碑 | 内容 | 验收结果 | Checkpoint |
|---|---|---|---|
| M0 | 环境与硬件验证 | GPU 冒烟全过（发现并规避 rocm 10.0 崩溃回归 + iGPU device 0 崩溃） | `b9c15eb` |
| M1 | 骨架与 Storage | SQLite schema/迁移幂等、Qdrant、Repository；pytest 18/18 | `a97e417` |
| M2 | Markdown Parser | M04 真实报告 64 sections / 130 blocks 全部正确，行号保留 | `6f900b6` |
| M3 | Semantic Chunker | 81 chunks；六项硬性 Gate（断表/断公式/跨节/行号/重ID/空块）全 0 | `0976160` |
| M4 | Chinese Lexical / FTS5 | Exact Hit@5 **1.000**（15 标识符）；FTS 三表一致；亚毫秒延迟 | `286abe9` |
| M5 | Dense Retrieval | Semantic 改写 Hit@5 **1.00**；Qdrant 407+351 点；CPU fallback 验证 | `18be24c` |
| M6 | Hybrid RRF | Hybrid Hit@5 **1.000** / MRR 0.865 > 任意单路；互补性实证 | `5a12a31` |
| M7 | Reranker + GPU Worker | NDCG 0.719→0.845（16 条 Mini Eval）；进程隔离 crash/restart/timeout 全过 | `1e2073b` |
| M8 | Incremental Index | Add/Modify/Rename/Delete/Crash/Repair 全 PASS；RENAMED 零重嵌入 | `fff8ffa` |
| M9 | Golden Evaluation | **Retrieval Quality Gate 5/5 PASS**（50 条人工标注 × 10 篇报告） | `d59480f` |
| M10 | FastAPI | 全套 API + 生命周期 + 真机冒烟；四方一致性 725=725=725=725 | `956c658` |
| M11 | React Frontend | 前端窗口交付：P0 三页 + P1 两页，build 无 TS 错误，真机 GUI 验证 | `9a4f90a` |

## 3. 核心质量指标（M9 Golden Evaluation，50 条人工章节级标注 / 10 篇报告 / 725 chunks）

### 3.1 Retrieval Quality Gate（Addendum §62）

| 条件 | 阈值 | 实际（hybrid_rerank） | 判定 |
|---|---|---|---|
| Hit@5 | >= 0.90 | **0.96** | PASS |
| MRR@10 | >= 0.75 | **0.869** | PASS |
| NDCG@10 | >= 0.80 | **0.897** | PASS |
| Exact Hit@5 | >= 0.95 | **1.00** | PASS |
| Semantic Hit@5 | >= 0.85 | **1.00** | PASS |

### 3.2 七路 Ablation（证明每层架构价值）

| Arm | Hit@5 | MRR@10 | NDCG@10 |
|---|---|---|---|
| terms only | 0.72 | 0.535 | 0.599 |
| trigram only | 0.54 | 0.455 | 0.466 |
| lexical combined | 0.78 | 0.599 | 0.652 |
| dense only | 0.94 | 0.773 | 0.779 |
| hybrid | 0.90 | 0.730 | 0.751 |
| hybrid + section boost | 0.92 | 0.724 | 0.758 |
| **hybrid + reranker** | **0.96** | **0.869** | **0.897** |

### 3.3 延迟（GPU RX 7900 XTX，batch 2）

索引吞吐：10 篇 725 chunks + 596 sections 全量 43.5s。
查询：hybrid P50 ~40ms；hybrid+reranker P50 ~1.0s / P95 ~2.3s（目标 3s 内）；
单路 lexical 亚毫秒。

## 4. 工程质量证据

- **测试**：后端 pytest **102 passed**（覆盖 parser/chunker/lexical/FTS/dense/
  search-engine/worker 隔离/增量索引/API）；前端 `tsc --noEmit` + vite build 无错误；
- **真机验证**：M10/M11 均以真实后端（GPU worker + Qdrant + SQLite）端到端验证，
  非 mock；GUI 全链路（搜索→上下文→行号定位）通过；
- **可解释性**：每条结果携带 dense_rank/terms_rank/trigram_rank/rrf/section_boost/
  reranker_score/pre_rerank_rank；debug=true 暴露各路 Top-K 与完整 timing 分解；
- **数据一致性**：SQLite（Canonical）与 Qdrant（可重建索引）四方计数一致 + repair 命令；
- **韧性**：GPU 推理独立 worker 进程（0xC0000005 只杀 worker），watchdog restart，
  连续 2 崩溃转 CPU fallback；staging 失败旧版本继续可搜索；
- **过程资产**：12 条 ADR、3 份评测报告（M7/M9 契约归档）、13 个里程碑 checkpoint、
  多窗口交接协议（HANDOFF_PROTOCOL.md）。

## 5. 规格书 Definition of Done 对照（spec §73）

已完成（21/24）：
源目录只读 ✅ / Markdown 结构化扫描 ✅（dev 语料 10 篇；全量归档为数据规模操作）/ 
增量索引 ✅ / SQLite Catalog ✅ / FTS Terms ✅ / FTS Trigram ✅ / Qdrant Dense ✅ /
Qwen Embedding ✅ / Hybrid RRF ✅ / Qwen Reranker ✅ / Metadata Filter ✅ /
Evidence Filter ✅ / Search Debug ✅ / Golden Set ✅ / Evaluation Report ✅ /
FastAPI ✅ / React Search UI ✅ / Document Viewer ✅ / Open Original ✅ /
Offline Mode ✅（模型本地化，HF_HUB 可离线）/ CPU Fallback ✅ / Documentation ✅

待完成（3/24，均已定义契约）：
- Windows 一键启动脚本（M12：start.ps1/stop.ps1，命令已具备仅差打包）
- Backup/Restore 与 Hardening（M13：备份、日志轮转、离线测试、损坏恢复）
- 全量归档索引执行（数据规模操作：改 config roots + `reindex.py scan`，耗时与语料量成正比）

## 6. 已知风险与遗留（详见 IMPLEMENTATION_STATUS.md Known Issues）

1. ROCm 锁定 torch 2.9.1+rocm7.13.0（10.0.0 Windows kernel-launch 回归，TheRock #4958）；
   升级必须重跑 smoke；GPU 推理已进程隔离，崩溃不影响后端；
2. causal 类型 Hit@5 0.75 为最弱项（50 条中 2 条）；调参必须走 Golden Set A/B；
3. cross_document MRR 0.64（Hit@5 已 1.00，排序待优化）；
4. Reranker P95 2.3s 接近 3s 目标上限（可调 candidate_k 或未来 4B 模型）；
5. Golden 标注由开发过程生成并经语料核对；产品化前建议补充独立人工标注；
6. 后端存在已登记的契约缺口（documents/{id}/chunks 列表端点），前端已用
   chunk_id 确定性枚举规避（见 HANDOFF_M11_DONE.md）。

## 7. 外部评估验证指南（可复现）

```powershell
# 0) 环境：Windows 11 + RX 7900 XTX + Docker Desktop；仓库 D:\AI-Knowledge-Engine
cd D:\AI-Knowledge-Engine

# 1) 后端测试基线（~2.5 分钟，需 Qdrant 运行 + GPU）
.venv\Scripts\python.exe -m pytest backend\tests\ -q          # 期望 102 passed

# 2) 启动后端（如未运行）
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --port 8765

# 3) 检索质量验证（GPU worker 自动拉起）
.venv\Scripts\python.exe backend\scripts\m9_eval.py            # 重算 7-arm 指标，对照 docs/M9_GOLDEN_EVALUATION.md

# 4) 前端（另开终端）
cd frontend; npm install; npm run dev                          # http://localhost:5173
# 搜索 "HBM4 的接口位宽是多少？" -> Top1 应命中 M04 HBM 代际规格表（rerank ~0.99）

# 5) 一致性检查
.venv\Scripts\python.exe backend\scripts\reindex.py check      # 期望 consistent: true
```

评估输入文件：`docs/IMPLEMENTATION_STATUS.md`（事实源）、`docs/M9_GOLDEN_EVALUATION.md`、
`data/golden_queries.jsonl`（50 条标注）、`data/m9_results.json`、`data/m9_failures.json`、
`docs/DEVELOPMENT_ADDENDUM_*.md`（用户下发约束）。
