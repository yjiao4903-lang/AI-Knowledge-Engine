# Implementation Status

## Current Milestone
M6 Hybrid Retrieval / Weighted RRF（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）
- [x] M3 Semantic Chunker（2026-08-29，Gate 六项全 0）
- [x] M4 Chinese Lexical / SQLite FTS5（2026-08-29，Exact Hit@5 = 1.000）
- [x] M5 Qwen3 Dense Retrieval（2026-08-29，Semantic Hit@5 = 1.00）

## In Progress
- [ ] M6

## M5 交付物
- `app/retrieval/dense.py`：DenseRetriever（Embedding + Qdrant 统一入口）
  - 设备经 get_inference_device()（preferred_gpu_name 匹配 cuda:1，iGPU 排除）
  - index_chunks：Chunk.embedding_text 批量向量化（batch 8 GPU / 2 CPU），
    payload 按 spec §25，点 ID 为 chunk_id 的确定性 UUID5（幂等 upsert）
  - index_sections：kb_sections_v1（title+path+heading+首段，spec §9.2）
  - search：query instruction 配置化，Qdrant query_points named vector "dense"
  - build_qdrant_filter：document_ids/domains/evidence_levels/content_types/
    date(DatetimeRange) 全部 prefilter
  - delete_document：按 document_id 清理两 collection（M8 复用）
- `backend/scripts/m5_index.py`：5 篇语料 -> 407 chunks + 351 sections 入 Qdrant
- `backend/scripts/m5_eval.py` + `docs/M5_DENSE_EVALUATION.md`

## M5 验收结果（docs/M5_DENSE_EVALUATION.md）
- Semantic Rewrite Hit@5：**10/10 = 1.00**（含 §31 两条改写查询），Top1 命中率 0.70
- 延迟：query embed+search P50 28.8ms（首次 1.3s 属模型冷启动）
- 索引耗时：407 chunks + 351 sections 全量 embedding 22.8s（GPU fp16 batch 8）
- CPU fallback：单条 query 32.1s（约 1/1100 速度），功能完整 PASS
- Metadata Filter：evidence_levels / document_ids prefilter 验证 PASS

## M4 交付物（摘要）
- `app/lexical/`：normalizer（NFKC + IDENT_RE 标识符保护）、
  tokenizer（jieba + tech_terms 预注册 + 占位符回填 -> lexical_text）、
  query_parser（统一 Safe Query Parser，双引号包裹杜绝 FTS 语法误解析）、
  fts_search（terms / trigram / combined RRF + timing）、corpus（5 篇语料构建）
- `app/retrieval/fusion.py`：weighted_rrf（M6 复用）
- Chunk 模型新增 lexical_text + to_db_dict()；LEXICAL_VERSION=4.0.0
- 新增 fixtures：M06（AI 基础设施/能源）、M09（AI 模型）、M14（宏观）、M18（生物医疗）

## M4 验收结果（docs/M4_EVALUATION.md）
- 索引一致性：chunks 407 = fts_terms 407 = fts_trigram 407 PASS
- Exact Hit@5：**15/15 = 1.000**；Chinese Hit@5：7/7 = 1.000
- 延迟：Terms P50 0.14ms / Trigram P50 0.21ms / Combined P50 0.37ms（亚毫秒级）
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
- pytest: 64 passed（dense 5、lexical 6、fts_search 8、chunker 11、m04 chunker 3、
  metadata 4、heading 3、m04 parser 6、migrations 5、repositories 6、
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
3. FTS5 查询语法问题已由统一 Query Parser 解决（M4 落地，单测固化）。
4. rocm-sdk test 的 hipconfig 控制台脚本存在 GBK 编码报错，不影响运行时。
5. 表格前的短引导句成为独立小 chunk，留待 M9 Golden Set 评估后决定
   是否增加"表前引导段附加"规则（Addendum §64/65）。
6. GPU Worker 进程隔离（Addendum §19/30/46）：M5 已实现 Provider 最小版本，
   Worker 进程隔离在 M7 必须完成。
7. 中文查询集"铜互连/推理算力/电网瓶颈"在 5 篇语料中无逐字匹配，
   M9 Golden Set 需改用章节级标注而非词面匹配。
8. Dense Top1 命中率 0.70（Hit@5 1.00）：Top1 质量预期由 M7 Reranker 提升。

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
