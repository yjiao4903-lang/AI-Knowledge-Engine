# P8 状态台账（唯一）

> 规范 §23 要求字段 + 交接说明 §7.2 的「假设 → 实验 → 判定」表。
> 每次完成工作包必须更新本文件；总台账见 `_meta/进度状态.md`。

## 0. 元信息

| 项 | 值 |
|---|---|
| 当前阶段 | **P8 WP1+WP2 完成（P8-0 冻结 + P8-2 仪器化 + 隔离探针 + 退化统计 + A/B/F 参数实验）；停在需用户决策关口（§6）** |
| 更新时间 | 2026-09-11 13:4x |
| corpus version | `p7_final`（documents 3,566；chunks **296,380（实验冻结态）**，此前在 296,380/296,385 间抖动，见 §5 阻塞 B1） |
| benchmark version | `legacy_v1`（冻结，50 题）；`development_v1` / `holdout_v1`：**仅结构与规范，题集待出** |
| best config | 生产基线 `A0`（fused_k30 / candidate_k24）；单参数最优 `F2`（权重 0.9/1.0/0.8）Hit@5 0.84（**+0.02，provisional**）。**无单参数配置达到 0.90** |
| 质量指标（全库，legacy canary） | Hit@5 **0.82** / MRR **0.640** / NDCG **0.678**（gate_pass=false，旧门线 0.90/0.75/0.80） |
| 质量指标（旗舰隔离 187 篇） | Hit@5 **0.90** / MRR **0.752** / NDCG **0.787** |
| latency（全库 hybrid_rerank） | p50 ~890 ms / p95 **~1310 ms**（p8_trace 复跑）；已发布 1015/1411 ms |
| 下一步唯一任务 | **无（停在用户决策关口）**；候选方向见 §6。若不决策，不推进调参/架构变更 |

## 1. WP1 交付物（均已落盘，可复现）

| 产物 | 说明 |
|---|---|
| `_golden/baseline_p7_20260911/` | P8-0 冻结基线（回归 JSON、配置快照+sha256、index_status、manifest、flagship ids、metrics_summary 含 Wilson CI） |
| `_golden/benchmark/{schema.json,legacy_v1/,development_v1/,holdout_v1/}` | Benchmark 数据结构；Legacy 50 题冻结（sha256 `aa0412a2…`） |
| `pipeline/p8_trace.py` | **核心仪器**：逐层 gold 名次 + candidate recall/presence + 双模式金标 + 自校验 + 配置覆盖 |
| `pipeline/p8_compare_isolation.py` | 隔离探针对照表与结论 |
| `pipeline/p8_degenerate_stats.py` | 退化章节统计 |
| `pipeline/p8_freeze_baseline.py` / `p8_bench_validate.py` | 冻结脚本 / 题集校验器 |
| `_golden/p8_experiments/A0_baseline_all/` | 全库基线 trace（自校验 pass） |
| `_golden/p8_experiments/isolation_flagship/` | 隔离探针 trace + `compare.md` |
| `p8_analysis/corpus_competition.json` | 隔离探针量化结论 |
| `p8_analysis/degenerate_sections.json` | 退化章节统计（H5） |

## 2. 关键实测事实（WP1）

1. **仪器可信**：`p8_trace.py` 在冻结语料上复现已发布回归，7 臂 Hit/MRR/NDCG 全部一致（Δ≤0.001），`self_check=true`。
2. **候选存在率（题级）**：dense50 0.86 / terms50 0.78 / trigram30 0.46 / **union50 0.96** / fusion30 0.84 / rerank24 0.84 / hit5 0.82。
   → 96% 的题其 gold 已进入候选池 ⇒ **主因是排序/融合，不是召回**（规范 §9 停止条件 3 方向）。
3. **H1 成立（旗舰隔离）**：Hit@5 0.82→**0.90**、MRR 0.640→0.752、NDCG 0.678→0.787；NO_RECALL 2→0；union50 0.96→1.00；fusion30 0.84→0.94。
   - 仅隔离即恢复前 5：`S01 W01 O02 X03`；隔离后仍失败：`E02 C01 C03 R01 X01`。
   - 残余分型：E02 = trigram 第 2 名被加权 RRF 埋到 fused 49–65（**融合权重**）；C01/C03 = fused 排名 33–40（**融合深度**）。
4. **H5 成立且尺度大（退化章节）**：`formal_report`（外资研报）220,635 chunks 占**74%**，仅 7,688 sections（**28.7 chunk/section**），标题 **99.9% 为占位**（`元信息` 覆盖 155,616 chunks）；`flagship` 为 1.1 chunk/section、0% 占位。
   - 根因经查为**源 markdown 抽取阶段丢失标题**（样例文件 24,133 行仅 2 个 `#` 标题），非引擎解析错误。
5. **层深事实**：`retrieval.rerank_k` 是**死配置**；真实重排截断由 `reranker.candidate_k=24` 决定，故 fused 第 25–30 名无重排机会。

## 3. 假设 → 实验 → 判定

| ID | 假设 | 验证实验 | 判定依据 | 状态 / 结论 |
|---|---|---|---|---|
| H1 | 语料竞争压制排序 | 旗舰隔离 vs 全库（50 题） | 隔离后 Hit@5 是否回升 | **成立**：+0.080（0.82→0.90），NO_RECALL 2→0 |
| H2 | 候选深度不足 | A 组 fused_k/candidate_k 阶梯 | LOW_DENSE_RANK 是否改善 | **不成立**：Hit@5 0.82→0.80/0.80/0.82，p95 +79%，触发停止规则 |
| H3 | 召回广度不足 | B 组 dense_k/terms_k=100 | NO_RECALL 是否进池 | **不成立**：W01/X03 进池但 fused 117/195，Hit@5 反降 0.80 |
| H4 | 融合权重偏置 | F 组 3–4 组权重 | gold 名次变化 | **部分成立**：F2(0.9/1.0/0.8) Hit@5 0.84（+0.02）、NDCG +0.01，量级不足 |
| H5 | 退化章节噪音 | 按 source_type 统计占位标题 | 与竞争强度相关性 | **成立（幅度大）**：74% chunk 标题缺失，`元信息` 占 52.5% |
| H6 | 重排能力上限 | 0.6B vs 4B | gold 进池却排低 | **暂不测**（须先满足规范 §19 三条件） |
| H7 | chunk 语义不完整 | gold chunk 上下文抽样 | 人工判读 | 待测（flagship p50 chunk 318 字，偏短，值得抽样） |

### 3.1 A 组实验（候选深度）

> 冻结索引（3,566 / 296,380）上重跑，A0=基线。

| ID | fused_k | candidate_k | Hit@5 | MRR | NDCG | p95(ms) | union50存在 | NO_RECALL | 结论 |
|---|---:|---:|---|---|---|---|---|---|---|
| A0 | 30 | 24 | 0.82 | 0.640 | 0.678 | ~1310 | 0.96 | 2 | 基线 |
| A1 | 40 | 32 | 0.80 | 0.637 | 0.678 | 1635 | 0.96 | 2 | 无收益 |
| A2 | 50 | 40 | 0.80 | 0.642 | 0.695 | 1897 | 0.96 | 2 | NDCG +0.017，Hit@5 −0.02 |
| A3 | 60 | 50 | 0.82 | 0.641 | 0.694 | 2348 | 0.96 | 2 | 回到基线，p95 +79% |

> **停止规则已触发（规范 §9.1）**：连续扩 K 的 Hit@5 提升 <0.02（实为 0/负）且 p95 大幅上升 → **停止扩大候选池**。
> **H2 判定：不成立**（候选深度不是主瓶颈）。逐题看：扩池把 C01/C03/C03/X01 从「fused 31–40 未进重排」变成「进入重排但仍排 5 名外」，
> 即瓶颈从深度**转移到重排质量**；W01/X03/O02/R01 在 A 组任何配置下都不在候选池（竞争性 NO_RECALL）；E02 fused 65，扩到 60 仍不足。
> 结论：P8 后续应转向 **重排/chunk** 与 **竞争治理（分池 routing）**，而非继续扩 K。

### 3.2 B / F 组实验（召回广度 / 融合权重）

| ID | 参数 | Hit@5 | MRR | NDCG | p95(ms) | union 存在 | 要点 |
|---|---|---|---|---|---|---|---|
| B2 | dense100/terms100, fused50/cand40 | 0.80 | 0.655 | 0.694 | 1908 | **1.00** | W01/X03 进池但 fused 117/195；O02 恢复（final 1）；Hit@5 反降、p95 +46% |
| F1 | 1.0/1.0/0.7 | 0.82 | 0.641 | 0.679 | 1273 | 0.96 | 与 A0 等同 |
| F2 | 0.9/1.0/0.8 | **0.84** | 0.647 | 0.688 | 1229 | 0.96 | S01 恢复；E02 fused 65→45；**唯一 Pareto 改善，provisional** |

> 汇总：**单参数杠杆最多 +0.02 Hit@5**；只有语料隔离到 0.90。→ 架构性答案是分层/routing，非单参数调优。

## 4. 数据完整性

- `consistent = true`（3,566 docs / 62,248 sections / 296,385 chunks；冻结实验态为 296,380）。
- 已发布 P7 回归为 `_golden/full_corpus_regression.json`（3,565 / 296,341），**原样冻结、未被覆盖**。
- config 快照 sha256 与 D 盘现网一致；引擎 `backend/app` 与 `config` 无我方改动。

## 5. 阻塞 / 风险

- **B1（工程，已缓解未根治）**：backend 启动/周期 reconcile 会**非确定性地重解析 `M04`/`M09`/`_最终报告`**：同一文件两次索引得到不同 chunks（M09 45↔77），并使 legacy 金标 `S03/S04` 间歇性 `unresolved`；chunk 总数在 296,380↔296,385 抖动。
  - 缓解：为跑受控实验，已**停止 backend** 冻结索引于 296,380（S03/S04 可解析）。
  - 未根治：可能需要引擎侧修复或固定索引流程（Safe Indexing Gate，P8-5/§14）。**属需用户/引擎维护方决策项。**
- **B2（语料）**：外资研报 tier 标题在抽取阶段丢失（74% chunk 无有效 heading）。修复需重抽取+局部重索引，触及红线（规范 §20），**需用户决策**。
- **B3（评测）**：Development/Holdout 题集需领域判断，**需用户参与**（P8-1 关键路径）。

## 6. 需用户决策的关口（到达即停）

1. **P8-1 新题集**：题型分层与题量（规范 Dev 100–150 / Holdout 50–100；交接建议先 30–50）。出题需领域判断。
2. **Legacy 门线定性**：检索质量回归 / 门线随规模重标定 / 并行（规范建议：Legacy 转 Canary，新门线由 Dev+Holdout 重建）。
3. **B1 索引非确定性**：是否推动引擎维护方修复 / 是否先固化索引流程再继续实验。
4. **B2 外资研报标题缺失**：是否允许局部重抽取+重索引（成本与红线）。
5. **延迟预算**：Fast p95 ≤1.5s / Research p95 ≤2.5–3.0s（实验软预算）是否确认。

## 7. 禁止事项提醒

沿用规范附录 A：不得降门线凑分、不得大范围网格搜索、不得换 embedding/直接上 4B、不得全量重分块/重嵌、不得改 D 盘引擎与原始语料、routing 不得直接上生产、不得用进程存活/chunks 增长当进度。
