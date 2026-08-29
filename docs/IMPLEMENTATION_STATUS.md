# Implementation Status

## Current Milestone
M7 Qwen3 Reranker（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）
- [x] M3 Semantic Chunker（2026-08-29，Gate 六项全 0）
- [x] M4 Chinese Lexical / SQLite FTS5（2026-08-29，Exact Hit@5 = 1.000）
- [x] M5 Qwen3 Dense Retrieval（2026-08-29，Semantic Hit@5 = 1.00）
- [x] M6 Hybrid Retrieval / Weighted RRF（2026-08-29，Hybrid Hit@5 = 1.000 / MRR 0.865）

## In Progress
- [ ] M7

## M6 交付物
- `app/retrieval/search_engine.py`：SearchEngine
  - 三路候选（dense 50 / terms 50 / trigram 30）-> Weighted RRF -> 去重
  - Section Parent Boost 1.08（section dense prior 前缀匹配 chunk_id，轻量非硬过滤）
  - Metadata 统一 post-filter（document/domain/content_type/evidence/date）
  - 三种模式 dense / lexical / hybrid；snippet 取首个查询词命中窗口
  - timing 全链路（embed/dense/terms/trigram/fusion/section/filter/total）
  - debug=true 返回各路 Top10 + boosted_sections + fused_top + filters
- `backend/scripts/m6_eval.py` + `docs/M6_EVALUATION.md`
- FusionConfig 新增 parent_boost / parent_boost_sections_k / parent_boost_enabled

## M6 验收结果（docs/M6_EVALUATION.md，16 条混合类型 Query）
- Hybrid：Hit@5 **16/16 = 1.000**，MRR@10 **0.865**，延迟 P50 75ms
- Dense only：Hit@5 0.938 / MRR 0.842；Lexical only：Hit@5 0.938 / MRR 0.844
- Gate PASS：Hybrid ≥ 单路。互补性实证：EXE:5000 由 lexical 补 dense（Dense 0/0.143），
  液冷语义查询由 dense 补 lexical（Lexical 0/0.167）
- 每条候选记录 dense_rank/terms_rank/trigram_rank/rrf/section_boost（可解释）

## M5 交付物（摘要）
- `app/retrieval/dense.py`：DenseRetriever（Embedding + Qdrant 统一入口）：
  get_inference_device() 选 cuda:1；index_chunks（payload 按 spec §25，确定性
  UUID5 幂等）；index_sections（kb_sections_v1，spec §9.2）；search（instruction
  配置化，named vector）；build_qdrant_filter（document/domain/evidence/
  content_type/date prefilter）；delete_document（M8 复用）
- `backend/scripts/m5_index.py` / `m5_eval.py` + `docs/M5_DENSE_EVALUATION.md`

## M5 验收结果（docs/M5_DENSE_EVALUATION.md）
- Semantic Rewrite Hit@5：10/10 = 1.00，Top1 命中率 0.70
- 延迟：query embed+search P50 28.8ms；索引 407+351 点 22.8s（GPU fp16 batch 8）
- CPU fallback：单条 query 32.1s（约 1/1100 速度），功能完整 PASS
- Metadata Filter prefilter 验证 PASS

## M4 交付物（摘要）
- `app/lexical/`：normalizer（NFKC + IDENT_RE 标识符保护）、
  tokenizer（jieba + tech_terms 预注册 + 占位符回填 -> lexical_text）、
  query_parser（统一 Safe Query Parser，双引号包裹杜绝 FTS 语法误解析）、
  fts_search（terms / trigram / combined RRF + timing）、corpus（5 篇语料构建）
- `app/retrieval/fusion.py`：weighted_rrf；Chunk 模型新增 lexical_text + to_db_dict()
- 新增 fixtures：M06（AI 基础设施/能源）、M09（AI 模型）、M14（宏观）、M18（生物医疗）

## M4 验收结果（docs/M4_EVALUATION.md）
- 索引一致性：chunks 407 = fts_terms 407 = fts_trigram 407 PASS
- Exact Hit@5：15/15 = 1.000；Chinese Hit@5：7/7 = 1.000
- 延迟：Terms P50 0.14ms / Trigram P50 0.21ms / Combined P50 0.37ms
- 特殊字符 - : / + . _ 全部无 FTS 语法错误

## M3 交付物（摘要）
- `app/chunking/`：chunk_models（三文本 + 稳定 chunk_id + content_hash + oversized）、
  semantic_chunker（prose 贪心打包 900/1400/2200 + 段落级 overlap；特殊块整体保全；
  公式附紧邻解释；不跨 Section；body 继承 reference/audit 父类型）、
  plain_text / embedding_text / qa（六项 Gate）；`backend/scripts/m3_stats.py`
- inference 显式配置（Addendum §17）：`config.inference` + `get_inference_device()`

## M3 验收结果（M04 fixture，816 行 -> 81 chunks）
- Chunk Length：Min 25 / P50 447 / P95 1142 / Max 1756（无 oversized）
- Content Types：causal_chain 13、prose 45、code 8、table 5、comparison 5、
  monitoring 1、reference 4
- Gate 六项全 0；人工抽样 22 chunks 通过（data/m3_sample_review.md）

## Tests（最新）
- pytest: 72 passed（search_engine 8、dense 5、lexical 6、fts_search 8、chunker 11、
  m04 chunker 3、metadata 4、heading 3、m04 parser 6、migrations 5、repositories 6、
  qdrant 1、health 2、sqlite capability 4）

## Known Issues
1. **核显导致 GPU kernel 崩溃**：Ryzen 7600X3D 核显被 HIP 枚举为 device 0，
   torch 在其上启动 gfx1100 kernel 直接 0xC0000005 崩溃。
   已在 `device.py` 按最大显存自动选择 `cuda:1`（RX 7900 XTX）规避。
   所有推理代码必须使用 device.py/get_inference_device() 返回的设备字符串，
   禁止裸写 "cuda"（Addendum §16）。
2. **rocm-sdk 10.0.0（stable index whl-next）Windows 回归**：kernel launch 段错误
   （amdhip64_7.dll，见 TheRock issue #4958）。已锁定 7.13.0。
   升级前必须重跑 `scripts/run_m0_smoke.ps1`（Addendum §18）。
3. rocm-sdk test 的 hipconfig 控制台脚本存在 GBK 编码报错，不影响运行时。
4. 表格前的短引导句成为独立小 chunk，留待 M9 Golden Set 评估后决定
   是否增加"表前引导段附加"规则（Addendum §64/65）。
5. GPU Worker 进程隔离（Addendum §19/30/46）：M7 必须完成。
6. 评测 ground truth 为词面匹配（chunk plain_text 含关键词），偏宽松；
   M9 Golden Set 改用人工章节级标注。
7. Dense Top1 命中率 0.70、Hybrid 个别 Top1 仍非最佳（词面 truth 偏宽松所致），
   预期由 M7 Reranker 提升后用同一 Query Set 复测对比。

## Decisions
- ADR-001 依赖管理：pip + pyproject.toml + requirements-lock.txt；不引入 poetry/uv，
  torch 不写入 pyproject dependencies（避免 PyPI CUDA wheel 覆盖），经 AMD 索引单独安装。
- ADR-002 ROCm 版本：锁定 torch 2.9.1+rocm7.13.0（legacy stable index），
  10.0.0 存在 Windows kernel-launch 崩溃回归，等待 AMD 修复后评估升级。
- ADR-003 设备选择：force_device > preferred_gpu_name > 最大显存 > CPU fallback
  （Addendum §17）；GPU 崩溃是进程级故障，包装脚本 `run_m0_smoke.ps1` 负责
  CPU fallback 重跑；Worker 进程隔离 M7 必须完成。
- ADR-004 SQLite 只读连接用 `PRAGMA query_only=ON`（Windows 上
  `file:...?mode=ro` URI 打开不稳定）；FTS 能力探针使用独立 in-memory 连接。
- ADR-005 FTS 为独立 virtual table（chunk_id UNINDEXED），由 ChunkRepository 与
  chunks 表同事务同步，删除文档时级联清理，避免 external-content 同步复杂性。
- ADR-006 Chunker 严格消费 Parser AST（Addendum §2）：无第二套 Markdown 正则；
  chunk_id 确定性生成（无 UUID），算法变更由 chunker_version 驱动 reindex。
- ADR-007 水平线（---）与纯 HTML 锚点行（<a id=...></a>）不产生内容块；
  body 子节继承 reference/audit 父节类型，供检索侧按 §22 排除。
- ADR-008 Qdrant 点 ID = 确定性 UUID5(chunk_id / section_id)（幂等 upsert，
  重建可复现）；Qdrant 仅存向量+payload，正文以 SQLite 为准（spec §9/26）。
- ADR-009 Hybrid 融合统一走 weighted_rrf（单路模式也用同一排序机制）；
  Metadata 过滤在 dense 路 prefilter、lexical 路 post-filter，结果一致；
  Section Parent Boost 只做乘法 prior（1.08），禁止按 section 硬过滤（spec §19）。
