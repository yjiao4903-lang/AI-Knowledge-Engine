# Implementation Status

## Current Milestone
M5 Qwen3 Dense Retrieval（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）
- [x] M3 Semantic Chunker（2026-08-29，Gate 六项全 0）
- [x] M4 Chinese Lexical / SQLite FTS5（2026-08-29，Exact Hit@5 = 1.000）

## In Progress
- [ ] M5

## M4 交付物
- `app/lexical/normalizer.py`：NFKC 规范化 + IDENT_RE（首类含 `+` 量词修复），
  Identifier Protector 保证 CoWoS-L/EXE:5000/60mV/dec/A16+ 等整体保留
- `app/lexical/tokenizer.py`：jieba + tech_terms 预注册 + 占位符保护回填 +
  轻量停用词 -> lexical_text；`config/tech_terms.txt`（ASCII + 中文专业词）
- `app/lexical/query_parser.py`：统一 Safe Query Parser（标识符/词项全部双引号
  包裹，杜绝 column filter / operator 误解析）
- `app/lexical/fts_search.py`：LexicalSearcher（terms / trigram / combined RRF）
  + timing
- `app/retrieval/fusion.py`：weighted_rrf（M6 复用）
- `app/lexical/corpus.py`：5 篇跨领域 fixture 语料构建（407 chunks 入库+FTS 同步）
- Chunk 模型新增 lexical_text + to_db_dict()；LEXICAL_VERSION=4.0.0
- 新增 fixtures：M06（AI 基础设施/能源）、M09（AI 模型）、M14（宏观）、M18（生物医疗）

## M4 验收结果（docs/M4_EVALUATION.md）
- 索引一致性：chunks 407 = fts_terms 407 = fts_trigram 407 PASS
- Exact Hit@5：**15/15 = 1.000**（>= 0.95 PASS）
- Chinese Hit@5：7/7 = 1.000（3 个词组语料无原文匹配已跳过）
- 延迟：Terms P50 0.21ms / Trigram P50 0.29ms / Combined P50 0.45ms（亚毫秒级）
- 特殊字符 - : / + . _ 全部无 FTS 语法错误
- pytest：59 passed

## Tests
- pytest: 59 passed（lexical 6、fts_search 8，新增 14 项）

## M3 交付物（摘要）
- `app/chunking/`：chunk_models（三文本 + 稳定 chunk_id + content_hash + oversized）、
  semantic_chunker（prose 贪心打包 900/1400/2200 + 段落级 overlap；特殊块整体保全；
  公式附紧邻解释；不跨 Section；body 继承 reference/audit 父类型）、
  plain_text / embedding_text / qa（六项 Gate）；`backend/scripts/m3_stats.py`
- inference 显式配置（Addendum §17）：`config.inference` + `get_inference_device()`

## M3 验收结果（M04 fixture，816 行 -> 81 chunks）
- Chunk Length Distribution（plain_text chars）：
  Min 25 / P25 167 / P50 447 / P75 772 / P90 979 / P95 1142 / Max 1756 / Mean 501.9
  （Max < hard_max 2200，无 oversized）
- Content Types：causal_chain 13、prose 45、code 8、table 5、comparison 5、
  monitoring 1、reference 4（M04 公式为行内 $...$，无 $$ 块，故 formula 0，
  公式附带逻辑由单测覆盖）
- Gate：Broken Table 0 / Broken Formula 0 / Cross-section 0 /
  Invalid Line Range 0 / Duplicate Chunk ID 0 / Empty Chunk 0 —— **全部通过**
- 人工抽样 22 chunks（data/m3_sample_review.md）：prose 语义完整、heading path
  含文档标题根、证据等级正确（含 [1,2] 数组）、表格完整未断、ASCII 拓扑图带
  fence 保真、行号与原文一致

## Tests
- pytest: 59 passed（lexical 6、fts_search 8、chunker 11、m04 chunker 3、
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
5. 表格前的短引导句（如 41 字符"……三次重大空间升维："）成为独立小 chunk，
   未并入表格 chunk。检索影响预计有限，留待 M9 Golden Set 评估后决定
   是否增加"表前引导段附加"规则（Addendum §65）。
6. GPU Worker 进程隔离（Addendum §19/30/46）：M5 先实现 Provider 最小版本，
   Worker 进程隔离在 M7 必须完成。
7. 中文查询集"铜互连/推理算力/电网瓶颈"在 5 篇语料中无逐字匹配
   （plain_text 不含该完整词组），ground truth 需在 M9 Golden Set 中用
   章节级标注解决，而非词面匹配。

## Decisions
- ADR-001 依赖管理：pip + pyproject.toml + requirements-lock.txt；不引入 poetry/uv，
  torch 不写入 pyproject dependencies（避免 PyPI CUDA wheel 覆盖），经 AMD 索引单独安装。
- ADR-002 ROCm 版本：锁定 torch 2.9.1+rocm7.13.0（legacy stable index），
  10.0.0 存在 Windows kernel-launch 崩溃回归，等待 AMD 修复后评估升级。
- ADR-003 设备选择：force_device > preferred_gpu_name > 最大显存 > CPU fallback
  （Addendum §17）；GPU 崩溃是进程级故障，包装脚本 `run_m0_smoke.ps1` 负责
  CPU fallback 重跑；Worker 进程隔离推迟至 M5/M7。
- ADR-004 SQLite 只读连接用 `PRAGMA query_only=ON`（Windows 上
  `file:...?mode=ro` URI 打开不稳定）；FTS 能力探针使用独立 in-memory 连接。
- ADR-005 FTS 为独立 virtual table（chunk_id UNINDEXED），由 ChunkRepository 与
  chunks 表同事务同步，删除文档时级联清理，避免 external-content 同步复杂性。
- ADR-006 Chunker 严格消费 Parser AST（Addendum §2）：无第二套 Markdown 正则；
  chunk_id 确定性生成（无 UUID），算法变更由 chunker_version 驱动 reindex。
- ADR-007 水平线（---）与纯 HTML 锚点行（<a id=...></a>）不产生内容块；
  body 子节继承 reference/audit 父节类型，供检索侧按 §22 排除。
