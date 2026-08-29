# Implementation Status

## Current Milestone
M0-M11 完成；**I0-I5 全部完成（2026-08-30）**：I0 Full Corpus Gate + Integration Contract、
I1-I3（Cognition Retrieval Proxy / Reports 融合 / Evidence Bridge）、I4 Unified Runtime、
I5 Backup/Restore/Hardening。
项目处于 Integration 路线 I0-I6（AI Research OS）。**整合事实源
`D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md` 为唯一进度来源**，本文件为 KE 侧镜像；
I4/I5 交付摘要与 Known Issues #14-21 见整合事实源。
下一步 I6（可选，Cognition Read-only Semantic Search，契约 docs/HANDOFF_I6.md，主计划 §48-50）。

## I0 交付摘要（2026-08-30，详见 docs/FULL_CORPUS_REPORT.md）
- **Full Corpus Index**：189 篇终版（v2 策略 ADR-013）/ 8828 sections / 9780 chunks；
  Failed 0、Encoding 0；排除 6970 全带 Exclusion Reason（DIR 6413/NON_FINAL 339/PROCESS 191/DUP 27）
- **一致性 Gate PASS**：chunks=fts_terms=fts_trigram=qdrant_points=9780（repair 清除 347 孤儿点）
- **人工抽样 100/100 PASS**（seed=20260829 可复现，full_corpus_sample.py）
- **全库 Golden Regression PASS**：Hit@5 0.920 / MRR 0.765 / NDCG 0.801（阈值 0.90/0.75/0.80），
  Exact/Semantic 1.00（full_corpus_regression.py，对生产索引非临时语料）
- **API/契约**：新增 GET /api/documents/{id}/chunks；health 增加 index_generation + gpu_worker；
  服务故障错误体 503 语义；INTEGRATION_CONTRACT.md + EvidenceReference V1 落地
  （D:\AI知识整合体系\docs\）
- **配置机制（ADR-015）**：KE_CONFIG/--config；config.yaml=生产全量，config.dev.yaml=dev 留档
- **解析器修复（ADR-014）**：复合中文数字（第十一章 曾解析为 ch0 撞名）+ section_id 撞名兜底
- **全量索引管线补 sections 向量**（M10 教训闭环）：随 chunks 同批嵌入 + 删除级联

## 交接机制
- `docs/HANDOFF_PROTOCOL.md`：多窗口交接流程（含 Integration 阶段补充约束）
- `docs/HANDOFF_M11_DONE.md`：M11 契约归档（前端窗口已交付）
- `docs/HANDOFF_I0.md`：**I0 任务契约**（Full Corpus Gate + Integration Contract，
  含交接方实测资产状态与工程要点）
- `docs/PROMPT_NEW_WINDOW_I0.md`：I0 新窗口启动提示词（用户复制即用）
- 主计划：`D:\AI知识整合体系\docs\AI研究知识体系整合_开发实施方案_V1.0.md`

## 路线变更说明
- 原独立 M12（Windows 打包）并入 I4 Unified Runtime；原 M13（Backup/Hardening）
  并入 I5（按数据价值重新分 Tier，见主计划 §43）；
- 两个系统不合并代码库/数据库：Cognition App = 认知控制平面（唯一写入权），
  AI Knowledge Engine = Evidence Engine（对认知数据只读），API 为唯一整合边界；
- 已核实就绪性风险：cognition-app 尚无 git 仓库（首次修改前须 init）；
  KE 当前索引为 dev 语料（10 篇），全量索引为 I0 首要任务。

## Completed
- [x] M0-M9 全部完成（2026-08-29；M9 Retrieval Quality Gate 5/5 PASS）
- [x] M10 FastAPI Productization（2026-08-29，API 11 项测试全过 + 真机冒烟）
- [x] M11 React Frontend（2026-08-29，前端窗口交付）

## In Progress
- （无）

## I0 完成登记
- [x] I0 Full Corpus Gate + Integration Contract（2026-08-30，本窗口交付）
- 产物：docs/FULL_CORPUS_REPORT.md、data/full_corpus_{stats,failures,sample,preflight,regression}.json、
  backend/scripts/full_corpus_{preflight,report,sample,regression}.py、
  backend/app/indexing/docid_policy.py、D:\AI知识整合体系\docs\{INTEGRATION_READINESS,INTEGRATION_CONTRACT}.md
- I1-I3 由本窗口（Window C）连续完成（ cognition-app @ 7828306）：
  I1 Retrieval Proxy / I2 Reports 融合 / I3 Evidence Bridge，KE 侧零改动；
  记录见 D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md
- HANDOFF_I1.md 已归档为 docs/HANDOFF_I1_DONE.md（含 I2/I3 完成记录）
- 下一阶段：I4 Unified Runtime（Window D），契约 docs/HANDOFF_I4.md，
  启动提示词 docs/PROMPT_NEW_WINDOW_I4.md

## M11 交付物（frontend/）
- 技术栈：React 18 + TypeScript + Vite 5 + React Router 6 + TanStack Query 5 + Ant Design 5（spec §43）
- `frontend/src/api/`：类型化 client（client.ts，错误体兼容 AppError/HTTPException）、
  TS 类型（types.ts，按 HANDOFF_M11 §2 真实契约逐一建模）、Query hooks（hooks.ts）
- 页面：
  - `/search`：搜索框 + Filters（Domain 联动文档/Evidence/Content Type/Document）+
    Mode 切换（Hybrid/Dense/Exact）+ Reranker/Debug 开关 + Top-K + 结果卡片
    （Rank/标题/heading path/Evidence 徽章/类型标签/snippet 查询词高亮/final+rerank
    分数/行号/chunk_id）+ 查看上下文跳转 + 复制引用 + timing 分解条 + Debug trace 面板
  - `/document/:id`：左侧 TOC 树（parent_section_id 建树）+ 右侧按 section 分块
    Markdown 渲染（react-markdown + GFM 表格）+ `?line=&chunk=` 跳转滚动高亮 +
    打开原文（POST open-original）
  - `/index`：四方计数（documents/sections/chunks/fts_terms/fts_trigram/qdrant_points）
    + 一致性徽章 + worker 健康（device/fallback/restarts/last_full_scan）+
    触发 scan + 单文档 reindex
  - `/settings`：脱敏配置分组展示（8 组，含 fusion 权重/query_instruction）
  - `/evaluation`：M9 Gate 五项判定 + 7-arm 指标表 + 分类型表 + 评测报告 Markdown
- dev 代理：vite.config.ts server.proxy `/api` → 127.0.0.1:8765（host 显式 127.0.0.1）

## M11 验收结果（Gate 全部 PASS）
- `npm run build`：tsc --noEmit 无错误 + vite 构建成功
- pytest 基线：102 passed（前端窗口未改后端，数字无变化）
- 真机 GUI 验证（uvicorn 8765 + vite 5173，真实后端非 mock）：
  - 搜索「HBM4 的接口位宽是多少？」hybrid+rerank：10 条结果，Top1 rerank 0.995（与
    M10 冒烟一致）；Evidence L1 过滤后全部结果仅 L1；Debug trace 面板显示候选数 80、
    各路来源与 fused_top；timing 分解条正常
  - 搜索 → 查看上下文 → `/document/M04?line=395`：文档 81 chunks 全量渲染、TOC 65 节点，
    行 395-401 chunk（M04:ch3-2:o1:0040，契约示例）自动滚动定位并高亮 ✓
  - `/index`：四方 725 一致 consistent ✓、worker alive cuda:1、scan 触发成功
  - `/settings`、`/evaluation` 渲染正确（Gate 全 PASS、best_arm hybrid_rerank）

## M11 契约缺口备忘（未改后端，前端已规避）
- 后端无「按文档列 chunks」端点，sections 端点不含 raw_text；前端利用 chunk_id
  确定性（{doc}:{section_path}:{ordinal}，ordinal 文档级连续无空洞，已在 10 篇全量
  验证）以单查探针法枚举（hooks.ts loadDocumentChunks，请求量 ≈ chunks+sections）。
  若后端未来提供 documents/{id}/chunks 列表端点，可替换该实现。

## M10 交付物
- `backend/app/api/`：
  - search.py：POST /api/search（filters/mode/rerank/top_k/debug，spec §32 契约）
  - documents.py：documents 列表/详情/sections、chunks 详情、open-original
    （路径白名单校验，Path Traversal 403 防护，spec §33/52）
  - index.py：status（四方计数+worker 健康）、scan、reindex-document、
    rebuild（显式 confirm="yes"）、jobs（spec §34）
  - evaluation.py：latest（m9_results.json + 报告）、run（golden 子集在线评测）
  - settings.py：脱敏配置
- `backend/app/main.py`：lifespan——InferenceManager 启动、startup reconcile
  （后台线程）、周期性 reconcile watcher（index_lock 串行化，spec §24/44）、
  shutdown 清理；AppError 统一错误体
- `backend/scripts/seed_dev_kb.py`：dev 语料库 seed（10 篇 -> data/dev_kb +
  data/catalog.db + kb_chunks_v1/kb_sections_v1；含 sections 重建）
- config.yaml：dev roots 指向 data/dev_kb；切全量归档改回后运行 reindex.py scan

## M10 验收结果
- pytest: 102 passed（新增 API 11 项：search 契约/模式/过滤、documents、
  path security 403、index status/jobs、reindex、rebuild confirm、evaluation、settings）
- 真机冒烟：uvicorn 127.0.0.1:8765，/api/health ok（worker cuda:1）、
  /api/search 带 reranker 正常（Top1 0.995）、debug trace 完整、
  index status 四方一致（chunks 725 = fts 725 = qdrant 725）
- 修复：kb_sections_v1 被 seed 脚本清空（已加入 sections 重建）；
  SQLite 跨线程（check_same_thread=False）

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
- pytest: **114 passed**（I0 窗口：102 基线 + docid_policy 9 + 解析器回归 2 + chunks 端点 1）
- 全库 Golden Regression: GATE PASS（见 docs/FULL_CORPUS_REPORT.md §4）

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
9. （M11）交接文档称 Node.js 已安装，实际系统无 Node：前端窗口使用便携版
   Node v22.14.0 于 `.tools/node/`（已 gitignore，不改全局配置）。复现构建：
   `export PATH="$PWD/.tools/node:$PATH"` 后执行 npm 命令。
10. （M11）后端缺「按文档列 chunks」端点，前端以 chunk_id 探针法枚举
    （见上方 M11 契约缺口备忘）；文档打开需 ~N+m 次本地请求，量级可接受。
    （I0 已补 GET /api/documents/{id}/chunks，前端可择机替换探针实现）
11. （I0）kb_sections_full_v1 含 159 个 v1 策略残段（chunks 已 repair 干净；
    sections 不在四方 Gate 内）——I1 前按 document_id 清理一次。
12. （I0）收录策略收紧后 rescan 不会自动删除被新策略排除的已索引文档
    （本次清库重扫解决）；策略调整需人工评估 catalog 增删。
13. （I0）全库稀释下 hybrid_rerank MRR 0.765 距阈值余量小（0.75）；
    NDCG 0.801 余量小（0.80）。C03/R01/X01 三条排序下降可作后续调参候选
    （禁止无 A/B 调参，主计划 §58）。

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
- ADR-013 全量语料收录与 doc_id 策略（v2 仅终版）：EXCLUDED_DIR/NON_FINAL/PROCESS/
  DUPLICATE 四类排除全留档；doc_id 规则 report_code > M 系 stem 回退 > 主题目录名 > stem，
  同 id 异内容 sha8 消歧。见 backend/app/indexing/docid_policy.py。
- ADR-014 解析器复合中文数字支持：_cn_to_int 一~九十九；section_id 撞名 :x{n} 兜底。
- ADR-015 配置切换：KE_CONFIG 环境变量 + reindex --config；config.yaml=生产全量
  （roots→D:/AI深度报告归档、catalog_full.db、kb_*_full_v1），config.dev.yaml=dev 留档。
