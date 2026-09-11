# P8-BENCH-01 状态报告 · 混合 Development / sealed Holdout 基准（2026-09-11）

**Issue**：LOCAL-DEV #36（父控制 #30）
**分支**：`local-dev/36-p8-mixed-benchmark`（基于权威 `main` `092e0753`）
**执行者**：LOCAL-DEV

## 0. 结论（先行）

已交付**确定性、可复现的题集生成与校验工具链**，并完成语料分层/反泄漏/密封/Legacy 冻结的全部结构校验；
但**机器自动出题在本语料上无法达到可辩护的金标质量**，因此按 Issue #36 明确的止损条款
（"stop at the largest defensible set and report the limiting factor rather than fabricating
low-quality queries"）**不发布 150 + 150 正式题集**，也未建立正式 sealed Holdout。

**限定因素**：这不是引擎/仪器问题（Legacy canary 在 exact head 复现 Hit@5 **0.82**，`self_check_pass=true`），
而是**金标规格**问题——自动抽取的"锚点实体"过于宽泛，单 chunk 金标对这类查询不是公平的相关性目标。

## 1. 已建成（可复用工具与框架）

| 产物 | 说明 |
|---|---|
| `docs/p8_review/scripts/p8_bench_build.py` | 确定性生成器：语料分层、seed 化 Dev/Holdout 文档切分、tier×query_type 配额、源内容锚定 gold、Holdout 密封 manifest。 |
| `docs/p8_review/scripts/p8_bench_verify.py` | 独立第二次校验：schema/枚举/唯一 id、chunk 解析与 `unresolved=0`、**锚点词回查源文本**、**source hash 冻结复核**、Dev/Holdout 目标文档不相交、cross_doc 同 split、Legacy 九文档排除、密封检查、Legacy 50 字节冻结校验、覆盖护栏。 |
| `docs/p8_review/benchmark/benchmark_manifest_v1.json` | freeze manifest：seed、tier/query_type 配额、各 split 组成统计与 SHA256、drops。 |
| `docs/p8_review/benchmark/benchmark_verification_v1.json` | 校验结果（全绿）。 |
| `docs/p8_review/benchmark/benchmark_coverage_v1.md` | 分层/题型覆盖表。 |
| `docs/p8_review/benchmark/development_v1/candidates_v0_machine_review_only.jsonl` | 机器候选集（150，**明确标注非门线题集**，供人工复核/改写）。 |

分层方案（按目录而非 chunk 体量）：flagship / broker_report（外资研报）/ daily_report（科技日报）/
trading_desk（中港+北美交易台）/ research_media（SemiAnalysis+公众号）/ discussion（即时讨论）；
**image_material（配图资料）经核查 100% 为 `（未 OCR）` 的 42 字占位 chunk，无可用正文**，
故 OCR 层改以跨层 `ocr_derived` 标注覆盖（证据等级 L2/OCR，650 篇，主要来自科技日报）。

## 2. 结构校验结果（全部通过）

| 校验 | 结果 |
|---|---|
| Development schema / 唯一 id / 枚举 / 禁 heading 锚定 | pass，n=150，`unresolved=0` |
| 锚点词回查源文本（第二次验证） | 0 error |
| source hash 与当前 catalog 一致（源未漂移） | pass |
| 分层护栏（单层 ≤35%，每层 ≥10%） | max 20.0% / min 10.0% |
| query_type 覆盖 | 7 类，配额满足（如 semantic_thesis 30、cross_doc 20…） |
| OCR 覆盖 | 19.3%（≥10%） |
| Dev/Holdout 目标文档不相交 | overlap = 0（158 / 161 docs） |
| Legacy 九 target 文档排除 | pass |
| Holdout 密封（不在仓库内） | pass |
| Legacy 50 字节冻结 | sha256 `aa0412a2…` 未变，pass |

## 3. 基线评测暴露的限定因素（核心证据）

同一冻结全量语料（3,566 docs / 296,380 chunks），同一引擎、未改任何检索参数：

| 题集 | hybrid_rerank Hit@1 | Hit@3 | Hit@5 | MRR | NDCG |
|---|---|---|---|---|---|
| **Legacy 50 canary**（冻结） | 0.52 | 0.72 | **0.82** | 0.640 | 0.678 |
| **Development 候选集（机器）** | 0.033 | 0.080 | **0.10** | 0.061 | 0.078 |

Legacy canary `self_check_pass=true`，证明引擎、Qdrant、重排与仪器健康；候选集的低分来自金标本身：

- 锚点词在**全语料**出现于**中位 ~290 篇文档 / ~1018 chunks**（均值 610 篇 / 4183 chunks）；
- **82%** 的锚点词出现在 >50 篇文档中，只有 **1.3%** 唯一文档、**2.7%** ≤3 篇文档；
- 用单个任意 chunk 作为宽泛实体查询（如"报告中 X 的现状"）的唯一金标，等价于要求检索命中
  数百个同等相关片段中的某一个——正例率天然接近 0，不能度量检索质量。

这一类失败在 `per_query` 中表现为 `NO_RECALL` / `FUSION`（gold 进不了候选/融合前 30），
而非 `RERANK`（排序问题），与上述定性一致。

## 4. 为什么机器出题无法达到可辩护质量

一个可辩护的检索基准金标需要**领域判断**来同时满足两点，而模板+词表抽取得不到：

1. **查询特异性**：把 query 写成对目标内容唯一可检索的信息需求（指定报告/主题，或复述一个具体主张），
   而不是"报告中 X 怎么样"这类数百片段同等相关的宽泛需求；
2. **相关性分级**：为这类查询给出多 chunk / 多文档的 grade 2–3 相关集合（或 section/doc 级相关性），
   而不是单一 chunk。

自动管线只能做到"该 chunk 确实包含锚点词"（**正确性**），无法判断"该 chunk 是这个问题的最佳答案"（**相关性**）。

## 5. 建议的下一步（人工在环）

沿用既有半自动工作流（`development_v1/README.md` 已定义）：

1. 人（领域判断）：选题 → 写 query（做到**指定报告/主题或具体主张**）→ 指定目标文档/章节范围 → 给 grade；
2. 工具：`p8_bench_build.py` 的锚点/实体抽取 + `p8_bench_validate.py --suggest-chunks` 产出候选 chunk_id；
3. 工具：`p8_bench_verify.py` 回查源文本、冻结 source hash、做 Dev/Holdout 反泄漏与密封校验；
4. 落盘 `questions_v1.jsonl` + 本 manifest 框架。

出题人（Development）与验收（Holdout）须分离；Holdout 题面/金标只存本地密封路径。

若要继续走自动/半自动路线，建议改变**查询语义**为"指定报告范围内的检索"（query 显式带报告名/主题），
并给出该报告内全部命中的多 chunk 金标——这属于题集设计变更，需 WEB-CONTROL 决策后再实施。

## 6. 边界与未做

- **未发布** 150+150 正式题集，**未建立**正式 sealed Holdout（生成方法未通过质量判定）。
- **未发布**无效的 Holdout 指标（避免以低质量金标误导门线）。
- 未改检索代码/权重/reranker/routing；未改 Legacy 50；未做全量破坏性重抽取/重分块/重索引。
- OCR/配图层无法从 `配图资料` 目录取证（非 OCR 占位），已如实记录。
- 无关本地改动 `config/config.yaml`、`docker-compose.yml` 未纳入提交。

## 7. 复现

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_build.py --split both ^
  --outdir <dir> --manifest docs\p8_review\benchmark\benchmark_manifest_v1.json
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_verify.py ^
  --development docs\p8_review\benchmark\development_v1\candidates_v0_machine_review_only.jsonl ^
  --holdout <sealed path> --out docs\p8_review\benchmark\benchmark_verification_v1.json
:: 基线（E 盘工作区）
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe pipeline\p8_trace.py --exp p8_bench01_dev ^
  --questions D:\AI-Knowledge-Engine\docs\p8_review\benchmark\development_v1\candidates_v0_machine_review_only.jsonl --split development
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe pipeline\p8_trace.py --exp p8_bench01_legacy_canary ^
  --questions D:\AI-Knowledge-Engine\docs\p8_review\benchmark\legacy_v1\golden_queries.jsonl --split legacy
```
