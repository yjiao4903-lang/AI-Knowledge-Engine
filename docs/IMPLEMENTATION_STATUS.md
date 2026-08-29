# Implementation Status

## Current Milestone
M8 Incremental Index（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）
- [x] M3 Semantic Chunker（2026-08-29，Gate 六项全 0）
- [x] M4 Chinese Lexical / SQLite FTS5（2026-08-29，Exact Hit@5 = 1.000）
- [x] M5 Qwen3 Dense Retrieval（2026-08-29，Semantic Hit@5 = 1.00）
- [x] M6 Hybrid Retrieval / Weighted RRF（2026-08-29，Hybrid Hit@5 = 1.000 / MRR 0.865）
- [x] M7 Qwen3 Reranker + GPU Worker（2026-08-29，NDCG 0.719 -> 0.845）

## In Progress
- [ ] M8

## M7 交付物
- `app/inference/protocol.py`：worker 任务协议（embed_query/embed_documents/rerank/
  health/shutdown + test_crash/test_sleep 测试任务）
- `app/inference/worker.py`：独立 OS 进程（spawn），一次加载双模型，Queue 通信，
  模块级入口保证 Windows spawn 可导入
- `app/inference/manager.py`：InferenceManager——call 请求-应答（task_id 匹配 + 超时）、
  watchdog（is_alive）、crash -> restart、连续 2 次崩溃 -> CPU fallback、
  runtime_profile.json 记录
- `app/retrieval/rerank.py`：RerankerService——官方输入模板（Instruct/Query/Document
  [Title/Section/Content Type/Evidence/正文]）、智能截断（heading + 查询词邻域 + 开头，
  不灌 chunk_id 等无关 metadata）、CPU 设备候选数上限
- SearchEngine 集成：rerank=True 时 Top24 重排，结果新增 reranker_score/pre_rerank_rank，
  debug trace 输出重排明细；rerank 失败自动退回 RRF 排序
- `backend/scripts/m7_worker_smoke.py` / `m7_eval.py`
- `data/m7_human_eval.jsonl`：16 条人工章节级标注（grade 3/2，按 heading 锚定），
  含"多节同词仅一节真答"陷阱型（Q01/Q16）与跨文档（Q15）
- 配置：reranker.enabled/batch_size/instruction/cpu_max_candidates；
  inference.worker_timeout_seconds/worker_start_timeout_seconds/max_consecutive_crashes

## M7 验收结果（docs/M7_EVALUATION.md，16 条人工标注 A/B）
| 指标 | Hybrid | Hybrid + Reranker |
|---|---|---|
| Hit@1 | 0.625 | **0.750** |
| Hit@3 | 0.812 | **0.938** |
| Hit@5 | 0.938 | **0.938**（不下降） |
| MRR@10 | 0.740 | **0.842** |
| NDCG@10 | 0.719 | **0.845** |
| P50 / P95 | 85ms / 1608ms | 1084ms / 2388ms（目标 1.5s/3s 内） |

- 16 条中 14 条 NDCG 提升、0 条回退；batch benchmark（真实文档）：batch 2 最优
  808ms/24docs（batch 8 因 padding 反而 1056ms）
- Worker：spawn 独立进程 PASS；crash -> restart PASS；timeout guard PASS；
  连续崩溃 CPU fallback 实现并测试 PASS；崩溃不影响 Backend 主进程
- 排序方向 bug 复盘：初版 rerank 排序键写反（未重排候选浮顶）导致 A/B 崩塌，
  已修复并以 debug trace 定位（教训记录于 Known Issues #9）

## Tests（最新）
- pytest: 84 passed（inference_worker 12：start/health/embed/restart/timeout/
  device/rerank order/empty/long-input/debug trace/no-rerank regression/CPU fallback）

## Known Issues
1. **核显导致 GPU kernel 崩溃**：Ryzen 7600X3D 核显被 HIP 枚举为 device 0，
   torch 在其上启动 gfx1100 kernel 直接 0xC0000005 崩溃。
   已在 `device.py` 按最大显存自动选择 `cuda:1`（RX 7900 XTX）规避。
   所有推理代码必须使用 device.py/get_inference_device() 返回的设备字符串，
   禁止裸写 "cuda"（Addendum §16）。M7 起 GPU 推理全部在 worker 进程内，
   崩溃不影响 Backend。
2. **rocm-sdk 10.0.0（stable index whl-next）Windows 回归**：kernel launch 段错误
   （amdhip64_7.dll，见 TheRock issue #4958）。已锁定 7.13.0。
   升级前必须重跑 `scripts/run_m0_smoke.ps1`（Addendum §18）。
3. rocm-sdk test 的 hipconfig 控制台脚本存在 GBK 编码报错，不影响运行时。
4. 表格前的短引导句成为独立小 chunk，留待 M9 Golden Set 评估（Addendum §60）。
5. 评测 ground truth：M4-M6 为词面匹配（偏宽松）；M7 Mini Eval 已升级为
   人工章节级 grade 3/2 标注；M9 扩展到 40-50 条 + 8-10 篇报告。
6. Reranker 延迟 P95 2.4s 接近 3s 目标上限；如需提速可考虑 candidate_k 下调
   或 4B 模型（当前锁定 0.6B，暂不动）。
7. Q06（供电电压）Hybrid Top10 未含目标节（词面 truth 下 MRR 0），
   reranker 将其拉升至 rank ~6；M9 需复查该 query 的召回。
8. Mini Eval 标注由开发过程生成（基于对语料章节的核对），M9 需引入
   真正独立的人工标注流程（Addendum §54）。
9. **教训**：Reranker 集成首跑质量崩塌（Hit@5 0.938 -> 0.125），根因是排序键
   方向写反且未重排候选浮顶；debug trace 直接定位。任何排序改动必须先跑
   A/B 对比再合入。

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
