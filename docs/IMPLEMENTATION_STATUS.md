# Implementation Status

## Current Milestone
M4 Chinese Lexical / SQLite FTS5（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）
- [x] M3 Semantic Chunker（2026-08-29，Gate 六项全 0）

## In Progress
- [ ] M4

## M3 交付物
- `app/chunking/chunk_models.py`：Chunk 模型（三文本 + 稳定 chunk_id
  `{document_id}:{section_id}:{ordinal:04d}` + content_hash + oversized）
- `app/chunking/semantic_chunker.py`：规则引擎，严格消费 M2 Section+Block
  （prose 贪心打包 target 900/soft 1400/hard 2200 + 段落级 overlap；
  特殊块整体成 Chunk；公式附带紧邻短解释；不跨 Section；根 section 跳过元数据
  blockquote；body 子节继承 reference/audit 父节类型）
- `app/chunking/plain_text.py`：Markdown 适度清洗，技术词/数字/公式/单位保留
- `app/chunking/embedding_text.py`：Document/Domain/Section/Content Type/Evidence 上下文模板
- `app/chunking/qa.py`：统计 + 六项硬性 Gate 校验
- `backend/scripts/m3_stats.py`：M04 统计 + 人工抽样输出（data/m3_sample_review.md）
- inference 显式配置（Addendum §17）：`config.inference`（force_device >
  preferred_gpu_name > 最大显存 > CPU），`device.get_inference_device()`

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
- pytest: 45 passed（chunker 11、m04 chunker 3、metadata 4、heading 3、m04 parser 6、
  migrations 5、repositories 6、qdrant 1、health 2、sqlite capability 4）

## Known Issues
1. **核显导致 GPU kernel 崩溃**：Ryzen 7600X3D 核显被 HIP 枚举为 device 0，
   torch 在其上启动 gfx1100 kernel 直接 0xC0000005 崩溃。
   已在 `device.py` 按最大显存自动选择 `cuda:1`（RX 7900 XTX）规避。
   所有推理代码必须使用 device.py/get_inference_device() 返回的设备字符串，
   禁止裸写 "cuda"（Addendum §16）。
2. **rocm-sdk 10.0.0（stable index whl-next）Windows 回归**：kernel launch 段错误
   （amdhip64_7.dll，见 TheRock issue #4958）。已锁定 7.13.0。
   升级前必须重跑 `scripts/run_m0_smoke.ps1`（Addendum §18）。
3. **FTS5 查询语法**：含 `-` / `:` 的标识符（CoWoS-L、EXE:5000）必须用双引号包裹，
   否则被解析为 column filter。M4 必须实现统一 Query Parser（Addendum §21-22）。
4. rocm-sdk test 的 hipconfig 控制台脚本存在 GBK 编码报错，不影响运行时。
5. 表格前的短引导句（如 41 字符"……三次重大空间升维："）成为独立小 chunk，
   未并入表格 chunk。检索影响预计有限（P50 447），留待 Golden Set 评估后决定
   是否增加"表前引导段附加"规则。
6. GPU Worker 进程隔离（Addendum §19）按计划推迟到 M5/M7 阶段实现。

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
