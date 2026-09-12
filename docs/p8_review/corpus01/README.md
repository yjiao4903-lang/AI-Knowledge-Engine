# P8-CORPUS-01 — foreign-research metadata/title recovery shadow experiment

> **状态（2026-09-12，LOCAL-DEV-A）**：shadow 实验完成，最终裁决 **`LIMITED_REPAIR`**。
> 生产语料/索引、benchmark gold、检索参数全部未动；全部实验在 A 专属隔离资源中进行。
> 机器可读证据：`corpus01_evidence.json`；确定性工具：`tools/`。

## 命题

> 外资研报大量 section heading 丢失、chunk 落入 `元信息`，是否是 corpus competition 和
> retrieval localization 下降的重要可修复原因？

## A. Corpus audit（全量，只读）

外资研报 tier：**2,097 篇 / 220,635 chunks（全库 74%）**。

- `元信息` chunk 占比 **100%**（220,635/220,635；P8 中期报告口径为 99.9%）；
- 有效 body heading 仅 **1.36 个/篇**（合计 ~2,325，几乎全是文档 H1）；
- 全部为 native-text 抽取（research_pdf 2,092 + daily_longimg 5，无 OCR 标记）；
- author/source family：Leada 1,274 / 小莫晕乎乎 502 / 小助手 230 / Hillwood 67 / 180K 24；
- report_code 碰撞（消歧后缀）1,652 篇；时间区间 2025-04-30 ~ 2026-09-04；
- chunks p50/p95 = 84/245，file size p50/p95 ≈ 110 KB / 347 KB。

## B. 确定性 shadow 抽样（89 → 139 篇评测集）

- **seed** `p8-corpus01-shadow-20260912`；规则与来源 SHA256 冻结于
  `shadow/audit/subset_manifest.json`（sha256 见 evidence JSON）。
- 强制纳入：Dev20 human-gold 目标文档 ∩ 外资研报（23 篇，修复臂）+ Legacy 9 目标文档（载体，不修复）。
- 分层补齐：author family × file-size 分位 round-robin（57 篇外资研报）→ 修复臂共 80 篇。
- 为使 Dev 20/20 全部可评测，追加 50 篇其他 tier 目标文档为**不修复载体** → 评测集 139 篇。

## C. Shadow repair（heading/title metadata recovery）

从原始 PDF（pymupdf font dict）做**字体驱动 heading 恢复**，注入 shadow markdown 副本：

- 候选 = 单行 block、字号 ≥ body+1.0、≤80 字符、bullet 几何缩进排除、跨页页眉/页脚抑制、
  必须能逐字匹配回 markdown 行；字号 ≥ body+3 → `##`，否则 `###`。
- **正文文本与 front matter 逐字节不变**；仅插入标题行。
- 结果：77/80 篇成功注入 **2,902 个 heading**（37.6 个/篇）；3 篇 PDF 缺失/为空跳过（保留原件）。
- 修复样例（Mizuho/ASML 报告）恢复出真实结构：`Takeaways / Valuation / Primary valuation: P/E /
  Investment risks / Financials / Analyst Certification …`。

## D. Determinism

- 同一不可变修复子集**完整重建两轮**（r1/r2，独立 SQLite + Qdrant collection）：
  docs 89 = 89，sections 3,896 = 3,896，chunks 17,504 = 17,504，FTS 计数相等；
  有序 (chunk_id, content_hash) 集合 SHA256 两轮**完全一致**（`89b1cbe6…`）。
- baseline 索引 vs 生产 catalog：共享 chunk_id（12,459 个）content_hash 不一致数 = **0**。
- 重复 reconcile 幂等（增量 scan UNCHANGED=89）。

## E. Corpus quality before/after（外资研报子集，80 篇）

| 指标 | baseline | shadow（修复后） |
|---|---|---|
| `元信息` chunk 占比 | **100%** | **5.0%** |
| 有效 body heading/篇 | 1.36 | **37.64** |
| sections/篇 | 11.2 | 43.8 |
| chunks/篇 | 175.9 | 196.7（+11.8%，section 重打包） |
| 重复 content 组 | 485 | 563 |

## F. Retrieval before/after（检索行为零改动；139-doc 隔离索引配对）

主口径为**文本级（粒度归一化）配对评测**：retrieved chunk 命中 gold 以文本包含判定，
消除修复导致的 chunk 重打包混杂。金标：Dev20 human gold（锚定 grade≥2）+ Legacy 50。

| 配对 | before → after |
|---|---|
| **Dev20 hybrid_rerank** | Hit@1/3/5 **0.90/0.90/0.95 → 0.90/0.90/0.95**，MRR 0.9183→0.9196，NDCG(诊断) 0.564→0.537 |
| Dev20 dense | Hit/MRR 全等 |
| Dev20 terms/trigram/lexical | Hit 全等，MRR ±0.03 内 |
| **Legacy50 hybrid_rerank** | Hit@1 **0.72→0.76**，Hit@3 **0.90→0.92**，Hit@5 **0.94→0.96**，MRR **0.8215→0.8515** |
| Legacy50 lexical arms | Hit@1 -2pp（FTS 词频被切分稀释），Hit@3/5 不变 |

- chunk 级原始 p8_trace 配对（未归一化）同场运行：Dev 全 arm 退化、Legacy hybrid_rerank 改善
  ——归因于重打包粒度差异（gold/词频随 chunk 切分变化），故以文本级口径为主判据。
- **sealed Holdout**：其 v2 目标文档不在本子集内，子集上不可评测；#39 密封聚合维持不变。

## G. Failure decomposition

- **lexical/FTS**：正文文本未变（`lexical_text` 不含 heading）→ FTS 命中按设计不变；
  legacy 侧 -2pp hit1 来自切分后词频稀释，非排序行为变化。
- **dense**：`embedding_text` 含 `heading_path`，但 Dev dense 臂 Hit/MRR 完全不变 →
  顶层 dense 暴露对修复不敏感。
- **corpus competition**：修复后 FR 文档在 top-10 的份额上升（Dev 0.325→0.375、Legacy
  0.104→0.12）——外资料不再是同质噪音，竞争参与更"有差别"，未见挤占 carrier 目标。
- **reranker**：Legacy hybrid_rerank 改善主要来自 reranker 对带真实 heading 的 FR 候选的
  区分能力（heading_path 是 reranker 输入）；Dev 侧持平。
- **duplicate suppression**：切分使重复 content 组 485→563，轻微负面。

## H. Cost

- 修复：77 篇 ~118s（≈1.5s/篇，CPU）。
- 全量重建估算：89 篇 scan ≈ 1,200–1,290s → ≈14.5s/篇（GPU embedding 主导）→
  2,097 篇 ≈ **8.5 小时**单机窗口。
- SQLite：89-doc 索引 227–236 MB；Qdrant：18,999 vs 20,844 points（+9.7%）。
- 回滚：删除 a43_* collection 与 shadow DB 即可；生产零接触。

## I. 最终裁决：`LIMITED_REPAIR`

理由：
1. 语料缺陷全量坐实（100% chunk 落 `元信息`），修复管线确定性/幂等/隔离全部验证通过；
2. 配对检索：Dev human-gold 文本级**持平**（无退化），Legacy canary**温和改善**——
   证明修复"无害且有局部收益"；
3. 不构成 `FULL_MIGRATION_CANDIDATE`：收益幅度有限、评测功效有限（20 Dev / 50 Legacy、
   139-doc 子集）、Dev rerank NDCG 略降；
4. **边界发现（须 WEB-CONTROL 裁决）**：section 级 chunking 下，heading 恢复必然改变
   chunk 打包（chunks/篇 +11.8%）——这是 chunk-boundary 政策问题，按 Issue #43 硬停条款
   不擅自跨越；若推进迁移需先裁决该政策并（建议）在 150+150 扩展基准上重测。

## 本目录内容

- `corpus01_evidence.json` — 全部聚合证据（audit/subset/repair/determinism/quality/retrieval/cost/verdict）
- `dev_per_query_rerank.json` — Dev 逐题 hybrid_rerank 文本级指标（Development split，可公开）
- `tools/` — 确定性工具（audit / sampling / repair / anchor-gold / text-level eval）
