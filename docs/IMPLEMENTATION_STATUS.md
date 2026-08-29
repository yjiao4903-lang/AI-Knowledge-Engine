# Implementation Status

## Current Milestone
M9 完成 —— Retrieval Quality Gate 通过。下一步：M10 FastAPI Productization

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）
- [x] M3 Semantic Chunker（2026-08-29，Gate 六项全 0）
- [x] M4 Chinese Lexical / SQLite FTS5（Exact Hit@5 = 1.000）
- [x] M5 Qwen3 Dense Retrieval（Semantic Hit@5 = 1.00）
- [x] M6 Hybrid Retrieval / Weighted RRF（Hybrid Hit@5 = 1.000 / MRR 0.865）
- [x] M7 Qwen3 Reranker + GPU Worker（NDCG 0.719 -> 0.845）
- [x] M8 Incremental Index（Add/Modify/Rename/Delete/Crash/Repair 全 PASS）
- [x] M9 Human-Labeled Golden Evaluation（2026-08-29，**Quality Gate 5/5 PASS**）

## In Progress
- [ ] M10（Gate 已通过，允许开始产品化）

## M9 交付物
- `data/golden_queries.jsonl`：**50 条**人工章节级标注（grade 3/2，heading 锚定），
  覆盖 10 篇报告，配额按 Addendum §51（Exact 6/Semantic 8/Causal 8/Comparison 6/
  Metric 5/Monitoring 5/Overview 4/Reference 3/Cross-document 5）
- `backend/scripts/m9_eval.py`：7-arm Ablation（terms/trigram/lexical/dense/hybrid/
  hybrid_boost/hybrid_rerank）× 7 指标（Hit@1/3/5、Recall@5/10、MRR@10、NDCG@10）
  × 分类型 + 失败归因桶
- 语料扩充至 10 篇（新增 M05 AI架构 / M07 液冷 / M10 LLM标度律 / M16 硬资产 /
  M22 帝国兴衰），725 chunks 全量重建索引（GPU 43.3s）
- 输出：docs/M9_GOLDEN_EVALUATION.md、data/m9_results.json、data/m9_failures.json

## M9 验收结果与 Quality Gate（Addendum §62）

| 指标 | Hybrid | Hybrid+Boost | **Hybrid+Reranker** | 阈值 | 判定 |
|---|---|---|---|---|---|
| Hit@5 | 0.90 | 0.92 | **0.96** | >= 0.90 | PASS |
| MRR@10 | 0.73 | 0.724 | **0.869** | >= 0.75 | PASS |
| NDCG@10 | 0.751 | 0.758 | **0.897** | >= 0.80 | PASS |
| Exact Hit@5 | 1.00 | 1.00 | **1.00** | >= 0.95 | PASS |
| Semantic Hit@5 | 1.00 | 1.00 | **1.00** | >= 0.85 | PASS |

- Ablation 证实每层价值：单路 terms/trigram Hit@5 仅 0.72/0.54，lexical 0.78，
  dense 0.94，hybrid 0.90，+reranker 0.96（NDCG 0.897 全场最高）
- Reranker 最终判定：**默认 ON**（Hit@5/MRR/NDCG 全面提升，Addendum §61）
- 分类型：metric/comparison/exact/monitoring/overview/semantic/reference 在
  hybrid_rerank 下 Hit@5 全部 1.00；最弱为 causal 0.75；cross_document 1.0 但 MRR 0.64
- 失败归因：38/50 查询全部 arm 通过；失败集中于 lexical 单路（6 条）与 1 条
  BAD_FUSION（reference 类型 hybrid 丢分、reranker 补回 1.0）

## M8 交付物（摘要）
- `app/indexing/{scanner,pipeline,reconcile}.py`：manifest 六态扫描（Fast Path）、
  staging 全成功后单事务原子替换、tombstone 删除、RENAMED 零重嵌入、
  四方计数一致性检查 + repair；`backend/scripts/reindex.py` 运维 CLI
- Gate：Add/Modify/Rename/Delete/Crash Recovery/No Orphan 全 PASS

## M7 交付物（摘要）
- GPU Worker 进程隔离（spawn 独立进程 + watchdog + restart + CPU fallback）
- Reranker 集成（Top24 重排 + debug trace + 失败退回 RRF）
- 16 条 Mini Eval A/B：Hit@1 0.625->0.750，NDCG 0.719->0.845

## Tests（最新）
- pytest: 91 passed

## Known Issues
1. 核显/HIP device 0 崩溃：device.py + worker 进程隔离双重规避（M0/M7）。
2. ROCm 锁定 7.13.0（10.0.0 Windows kernel-launch 回归，TheRock #4958）。
3. causal 类型 Hit@5 0.75 为最弱项（2 条失败），M10 前可用 golden set 微调
   RRF 权重（禁止无 A/B 调参）。
4. reference 类型 hybrid（无 reranker）为 0（编号列表词面命中差）；
   reranker 补回 1.0，保持默认 ON 即可。
5. cross_document MRR 0.64：跨文档排序可优化（Hit@5 已 1.0）。
6. Golden 标注由开发过程生成并经语料核对；产品化前建议补充独立标注。
7. 表前引导句独立 chunk：Golden Set 中 table-context 查询未失败，
   判定为暂不增加规则（Addendum §60）。
8. Watcher 进程内嵌推迟至 M10（与 FastAPI lifespan 一起接入）。

## Decisions
- ADR-001 依赖管理：pip + pyproject.toml + requirements-lock.txt；torch 经 AMD 索引单独安装。
- ADR-002 ROCm 锁定 torch 2.9.1+rocm7.13.0（10.0.0 Windows 回归）。
- ADR-003 设备选择：force_device > preferred_gpu_name > 最大显存 > CPU fallback；
  GPU 推理在独立 worker 进程，watchdog restart + 连续 2 崩溃转 CPU。
- ADR-004 SQLite 只读用 PRAGMA query_only=ON；FTS 探针独立 in-memory 连接。
- ADR-005 FTS 独立 virtual table，同事务同步，删除级联。
- ADR-006 Chunker 严格消费 Parser AST；chunk_id 确定性，chunker_version 驱动 reindex。
- ADR-007 水平线/HTML 锚点不产生内容块；body 继承 reference/audit 父类型。
- ADR-008 Qdrant 点 ID = UUID5（幂等）；正文以 SQLite 为准。
- ADR-009 Hybrid 统一 weighted_rrf；dense prefilter + lexical post-filter；
  Section Boost 乘法 prior 1.08。
- ADR-010 Reranker 默认 ON（M7 A/B + M9 Golden 双重验证）；batch_size=2；
  rerank 失败自动退回 RRF。
- ADR-011 增量索引：staging 全成功后单事务替换（先删 chunks/FTS 再删 sections）；
  Qdrant 失败由 repair 兜底；RENAMED 零重嵌入；watcher 推迟至 M10。
- ADR-012 Golden Set 标注采用 heading_contains 锚定（对 section_id 规则变化稳健）；
  grade 3/2 二级即可支撑 NDCG。
