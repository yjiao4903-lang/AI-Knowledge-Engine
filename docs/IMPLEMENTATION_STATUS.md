# Implementation Status

## Current Milestone
M9 Human-Labeled Golden Evaluation（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）
- [x] M3 Semantic Chunker（2026-08-29，Gate 六项全 0）
- [x] M4 Chinese Lexical / SQLite FTS5（2026-08-29，Exact Hit@5 = 1.000）
- [x] M5 Qwen3 Dense Retrieval（2026-08-29，Semantic Hit@5 = 1.00）
- [x] M6 Hybrid Retrieval / Weighted RRF（2026-08-29，Hybrid Hit@5 = 1.000 / MRR 0.865）
- [x] M7 Qwen3 Reranker + GPU Worker（2026-08-29，NDCG 0.719 -> 0.845）
- [x] M8 Incremental Index（2026-08-29，Add/Modify/Rename/Delete/Crash/Repair 全 PASS）

## In Progress
- [ ] M9

## M8 交付物
- `app/indexing/scanner.py`：manifest 扫描（size+mtime_ns Fast Path 跳过 SHA256；
  NEW/UNCHANGED/MODIFIED/DELETED/RENAMED/ERROR 六态；RENAMED 按同 sha256 认领，
  MODIFIED 内容未变时自动降级 UNCHANGED）
- `app/indexing/pipeline.py`：IndexPipeline——staging（读/解析/分块/嵌入全部成功后）
  才进入 SQLite 单事务原子替换（chunks/FTS 先删、sections 后删避免 FK），
  再 Qdrant delete-by-document + upsert；remove_document（tombstone + 级联清理）；
  rename_document（仅更新 manifest，零重嵌入）；EmbedderAdapter（worker 适配）
- `app/indexing/reconcile.py`：per-document 一致性检查（chunks/FTS×2/Qdrant 四方计数）
  + repair（孤儿点删除 + 缺失文档从 SQLite 重嵌入重建）
- `backend/scripts/reindex.py`：scan / check / repair 运维 CLI
- 测试使用 tmp 知识库 + 独立测试 collection（kb_chunks_m8test），不触碰真实知识源

## M8 验收结果（Addendum §45-46 Gate）
- Add PASS / Modify PASS（新内容可检索、旧内容消失、四方一致）
- Rename PASS（零重嵌入，仅 manifest 更新）
- Delete PASS（tombstone + FTS/Qdrant 清理）
- Crash Recovery PASS（staging 失败 -> 错误记录 + 旧版本继续可搜索 + 四方一致）
- No Orphan FTS / No Orphan Qdrant PASS（repair 用例：人为删除 Qdrant 点后恢复）
- pytest: 91 passed（新增 indexing 7 项）

## M7 交付物（摘要）
- `app/inference/{protocol,worker,manager}.py`：GPU Worker 进程隔离（spawn 独立进程、
  watchdog、crash restart、连续 2 次崩溃 CPU fallback、runtime_profile 记录）
- `app/retrieval/rerank.py` + SearchEngine rerank 集成（Top24 重排 + debug trace +
  失败退回 RRF）
- 人工章节级 Mini Eval 16 条（data/m7_human_eval.jsonl）+ A/B（docs/M7_EVALUATION.md）

## M7 验收结果（docs/M7_EVALUATION.md）
- Hit@1 0.625->0.750，Hit@3 0.812->0.938，Hit@5 0.938 持平，
  MRR 0.740->0.842，NDCG 0.719->0.845（16 条中 14 条提升 0 回退）
- P50 1084ms / P95 2388ms（目标 1.5s/3s 内）；batch=2 最优（真实文档 benchmark）
- Worker crash/restart/timeout/CPU fallback 测试全部 PASS

## Tests（最新）
- pytest: 91 passed（indexing 7、inference_worker 12、search_engine 8、dense 5、
  lexical 6、fts_search 8、chunker 11、m04 chunker 3、metadata 4、heading 3、
  m04 parser 6、migrations 5、repositories 6、qdrant 1、health 2、sqlite capability 4）

## Known Issues
1. **核显导致 GPU kernel 崩溃**：Ryzen 7600X3D 核显被 HIP 枚举为 device 0，
   torch 在其上启动 gfx1100 kernel 直接 0xC0000005 崩溃。
   已在 `device.py` 按最大显存自动选择 `cuda:1`（RX 7900 XTX）规避。
   GPU 推理全部在 worker 进程内，崩溃不影响 Backend（Addendum §16）。
2. **rocm-sdk 10.0.0（stable index whl-next）Windows 回归**：kernel launch 段错误
   （amdhip64_7.dll，见 TheRock issue #4958）。已锁定 7.13.0。
   升级前必须重跑 `scripts/run_m0_smoke.ps1`（Addendum §18）。
3. rocm-sdk test 的 hipconfig 控制台脚本存在 GBK 编码报错，不影响运行时。
4. 表格前的短引导句成为独立小 chunk，M9 Golden Set 评估后决定
   是否增加"表前引导段附加"规则（Addendum §60）。
5. Reranker 延迟 P95 2.4s 接近 3s 目标上限。
6. M7 Mini Eval 标注由开发过程生成，M9 需引入独立人工标注流程（Addendum §54）。
7. Q06（供电电压）Hybrid Top10 未含目标节，reranker 拉升至 rank ~6；
   M9 复查该 query 召回。
8. M8 测试曾因 cfg.knowledge_base.roots 未指向 tmp 而扫描真实知识库挂起——
   已修复；任何索引测试必须显式覆盖 roots。
9. M8 教训：事务内删除顺序（sections 先于 chunks）触发 FK 失败导致 MODIFIED
   全量失败；已修正并写入测试（任何 schema/顺序改动必须重跑 M8 全套）。
10. Watcher：V1 以周期性全量 manifest reconcile（reindex.py scan）替代 watchdog
    进程内嵌；进程内 watcher（watchdog 库或轮询线程）推迟至 M10 与 FastAPI
    启动流程一起接入（spec §24：watcher 不能是唯一机制，reconcile 已具备）。


## Decisions

- ADR-001 依赖管理：pip + pyproject.toml + requirements-lock.txt；不引入 poetry/uv，
  torch 不写入 pyproject dependencies（避免 PyPI CUDA wheel 覆盖），经 AMD 索引单独安装。
- ADR-002 ROCm 版本：锁定 torch 2.9.1+rocm7.13.0（legacy stable index），
  10.0.0 存在 Windows kernel-launch 崩溃回归，等待 AMD 修复后评估升级。
- ADR-003 设备选择：force_device > preferred_gpu_name > 最大显存 > CPU fallback
  （Addendum §17）；GPU 推理全部在独立 worker 进程内（M7），崩溃只杀 worker，
  manager watchdog 自动 restart，连续 2 次崩溃转 CPU fallback 并写 runtime_profile。
- ADR-004 SQLite 只读连接用 `PRAGMA query_only=ON`；FTS 能力探针使用独立
  in-memory 连接。
- ADR-005 FTS 为独立 virtual table，由 ChunkRepository 同事务同步，删除级联清理。
- ADR-006 Chunker 严格消费 Parser AST；chunk_id 确定性生成，变更由
  chunker_version 驱动 reindex。
- ADR-007 水平线与纯 HTML 锚点行不产生内容块；body 子节继承 reference/audit
  父节类型。
- ADR-008 Qdrant 点 ID = 确定性 UUID5（幂等 upsert）；Qdrant 仅存向量+payload，
  正文以 SQLite 为准。
- ADR-009 Hybrid 融合统一走 weighted_rrf；Metadata 过滤 dense 路 prefilter、
  lexical 路 post-filter；Section Parent Boost 只做乘法 prior（1.08）。
- ADR-010 Reranker 默认开启（A/B 证明 NDCG/MRR/Hit@1 全面提升且 Hit@5 不降）；
  batch_size=2（真实文档 benchmark，batch 8 因 padding 反而更慢）；
  rerank 失败时自动退回 RRF 排序，不阻塞搜索。
- ADR-011 增量索引：staging 全部成功后才进入单事务替换（事务内先删 chunks/FTS 再删
  sections 避免 FK）；Qdrant 替换在 SQLite 提交后进行，失败由 reconcile repair 兜底；
  RENAMED 零重嵌入；V1 watcher 以周期性 reconcile 替代，进程内 watcher 推迟至 M10。
