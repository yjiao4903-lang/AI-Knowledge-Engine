# P8-BENCH-02 盲化人工相关性判定（blinded human adjudication）

> **状态（2026-09-11，批次 v2）**：工具链已交付并通过无 GPU 自检（24/24）。
> **v1 校准包已由 WEB-CONTROL 作废**（query 不自足，见 `superseded/README.md`），并由
> **v2 替代批次**取代：Dev 20 在 `development_calibration_v2/`，sealed Holdout 10 在仓库外。
> v2 批次先通过 **Query Validity Gate**（`query_validity_audit_v2.json`：Dev 20/20、Holdout 10/10）。
> **人工领域判定尚未录入**，因此 `human_review_complete = false`，校准门线**未完成**。
> 本目录内的包与 key 只是待判材料，不是证据。

## 为什么需要这一层

2026-09-11 WEB-CONTROL 更正（PR #41 REQUEST_CHANGES）：

> `p8_bench_pool.py::grade_chunk()` 用 token 包含 / 正则谓词机械判定相关度，其产物是
> **机器预标注 `auto_prelabel`**，不是人工相关性判定。因此此前"43/60 Dev、24/40 Holdout 池内无
> grade-3"与 "Dev Hit@5 = 0.167" **只能说明自动 rubric 与检索池不相交**，不能用来推断检索质量，
> 也不能用来判定 benchmark 无效。

因此相关性判定必须由**人工领域审阅**给出，并且要与自动预标注**分开持久化、可审计、可冻结**。

## 证据分级（引用任何数字前先看这里）

| `reviewer_kind` | 含义 | 能否作为门线证据 |
|---|---|---|
| `human` | 人类领域审阅者 | 是（且必须覆盖全部校准题） |
| `agent_assisted` | 模型/工具辅助判定 | 否，仅作流水线验证或参考 |
| `selftest` | 自动化 plumbing 自检的合成判定 | 否，严禁引用 |
| （无，`auto_prelabel`） | `p8_bench_pool.py` 的机械预标注 | 否，不得用于效度/检索质量结论 |

`import` 产出的 freeze 文件里 `human_review_complete` 只有在**全部校准题都由 `human` 判定且无缺题**
时才为 `true`。

## Query Validity Gate（人审前置门）

人工判定前，query 必须先过 `p8_bench_query_gate.py`（确定性预过滤器）：

- 不得含未解析指代（`报告中/文中/该报告/该机构/上述/本文/前文…`）；
- 不得含泛化占位维度（`相关指标 / 数量上的差异 / 有什么变化 / 起了什么作用 / 怎么样 / 情况如何`）
  除非已具体化；
- 必须显式命名 ≥1 实体（latin 专名或中文专名词表）与 ≥1 具体化维度
  （营收/毛利率/价格/产能/capex/概率/机制/份额/风险…）；
- `reject` 的题在人审前重写或替换；只有通过 Gate 的冻结 query 才进入人审包。

当前 v2 批次：Dev **20/20**、sealed Holdout **10/10** 通过（`query_validity_audit_v2.json`）。

## 工作流

```
export  →  人工判定（盲化）  →  import（只由人工 grade 重算 gold）  →  report（auto vs 人工分歧）
```

### 1. export：生成盲化人审包

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py export ^
  --questions <v2 池化冻结题集：.p8_local_dev\v2\development_v2_frozen.jsonl> ^
  --split development --n 20 --version-tag v2 ^
  --outdir docs\p8_review\benchmark\adjudication\development_calibration_v2 ^
  --keydir docs\p8_review\benchmark\adjudication\_keys ^
  --pool-audit docs\p8_review\benchmark\adjudication\authored_v2\development_pool_audit_v2.json
```

产出（Dev 版本入库）：

| 文件 | 用途 |
|---|---|
| `packet_<split>_calibration_v2.jsonl` | 机器可读人审包：冻结 query + 打散候选 + 源文本 |
| `packet_<split>_calibration_v2.manifest.json` | 抽样/盲化/池化参数 + SHA256 |
| `review_form_<split>_calibration_v2.md` | 人读审阅表（粘贴/填表用） |
| `judgments_<split>_calibration_v2.template.jsonl` | 判定录入模板（已预置 cand_id 与 `grade: null`） |
| `_keys/key_<split>_calibration_v2.json` | **盲化映射**（cand_id → chunk_id / 视图名次 / 预标注 grade） |

盲化保证：包内**不含**检索视图归属、视图内名次、融合分数、`auto_prelabel` grade；候选顺序按
`random.Random("<seed>|<qid>|shuffle")` 确定性打散，`cand_id` 为打散后位置，不携带名次信息。

> 审阅人只看 `review_form_*.md` 或 `packet_*.jsonl`，**不要打开 `_keys/`**，否则盲化失效。

### 2. 人工判定

按 `adjudication_schema_v1.json` 填写 `judgments_*.template.jsonl`：

- `status`：`accept` / `rewrite` / `reject` / `ambiguous`；
- `grades[].grade`：0/1/2/3（3=直接回答，2=实质支撑，1=主题相关但不足，0=无关）；
- **candidate-level completeness（强制）**：`accept` / `rewrite` 的每一题必须把该题人审包内的
  **每一个候选都判定且仅判定一次** —— 缺候选、未知候选或重复候选都会被 `import` 直接拒绝。
  这是 pooled false-negative 审计的前提；部分判定会静默缩小相关集合并污染分歧统计。
- `reject` / `ambiguous` 是**题目级**处置，不要求逐候选判定；它们会被显式排除出 gold 与全部指标。
- `accept` / `rewrite` 的题必须至少 1 个 grade-3；`rewrite` 必须填 `final_query`；
- 填 `reviewer` / `reviewer_kind: human` / `reviewer_version` / `reviewed_at`（ISO8601）。

### 3. import：只由人工 grade 重算 gold

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py import ^
  --judgments <filled.jsonl> --key docs\p8_review\benchmark\adjudication\_keys\key_development_calibration_v2.json ^
  --questions docs\p8_review\benchmark\adjudication\authored_v2\development_v2_frozen.jsonl ^
  --split development --require-complete ^
  --adjudication-out <adj.jsonl> --gold-out <gold.jsonl> --freeze-out <freeze.json>
```

> **批次必须同源**：`--questions` 必须是生成该 key 的同一份冻结题集
> （v2 = `adjudication\authored_v2\development_v2_frozen.jsonl`）。
> `build_gold_record()` 会从 `--questions` 继承冻结记录来生成 human gold，因此
> **v2 judgments + v1 frozen record** 的混用会产生错误金标。`import` 现在对此 fail-fast：
> judgment qid 不在 `--questions` 中、或 key 与 `--questions` 的 query 文本不一致时直接拒绝。

- gold **只**由人工 grade ≥2 生成（`evidence_class = human_adjudicated`）；
- 同时做人工判定后的 false-negative 审计，把"人工判为相关但预标注 gold 未收录"的块记入
  `judging.fn_added_after_human_audit`；
- `reject` / `ambiguous` 的题排除出 gold 并单独记录；
- freeze 输出 `candidate_completeness`（`accepted_or_rewritten` / `fully_graded` /
  `coverage` / `incomplete_queries` / 逐题 `graded` vs `packet`），并据此决定
  `human_review_complete`：**未达 100% 候选覆盖一律为 false**；
- `--require-complete` 额外要求覆盖**全部**校准题（不只是候选级完整）；
- `--split holdout` 时若输出路径位于仓库内会**直接拒绝执行**（密封条款）。

### 4. report：auto_prelabel vs 人工分歧

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py report ^
  --judgments <adj.jsonl> --key <key.json> --split development --out <report.json> --md <report.md>
```

输出：candidate 级 grade 完全一致率 / ±1 一致率、二值相关（≥2）precision/recall/F1、
grade-3 集合 Jaccard、人工相关但预标注漏收的块数、以及人审池内的 benchmark-side recall。

指标**只由 `accept` / `rewrite` 的题计算**；`reject` / `ambiguous` 在报告的
`excluded_from_metrics` 区块中逐题列出（status + notes）并被完全排除。报告同时输出
`candidate_completeness`，且 `human_review_complete` 采用与 `import`/freeze 相同的判定口径。

正式指标仍由既有评测器在**人工 gold** 上重算（不改检索行为）：

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_trace.py ^
  --exp p8_bench02_development_human --questions <gold.jsonl> --split development
```

## 确定性自检（无 GPU）

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py self-test
```

覆盖：schema 拒绝（未知 cand_id / 重复 cand_id / 非法 grade / accept 无 grade-3 /
**accept 部分候选判定** / rewrite 缺 final_query / 缺 reviewer）、gold 往返只取人工 grade、
FN 补入、freeze 哈希稳定、reject 不入 gold、**候选级完整度标志**（缺题 / 非 human /
候选不完整 → `human_review_complete=false`；reject 不要求候选覆盖也不阻塞标志）、
**report 将 reject/ambiguous 排除出指标**、Holdout 密封护栏、抽样确定性、family 覆盖。
当前 **24/24 通过**。

## 已披露限制

- **有界池**：候选为 4 个冻结视图 top-N 的有界轮转抽样（Dev 每题的候选上限 20），未出现在包内的块
  按不相关计（标准 pooling 假设）。因此本校准**不是**全语料穷举的完整相关性集合。
- **跨 split 排除**：池内属于另一 split 的候选被排除（Anti-leakage），数量记录在包的 manifest
  `selection.cross_split_candidates_excluded`。
- **校准子集**：`--n` 为校准规模（Dev 20 / Holdout 10），用于在扩展到 60+40 之前验证判定口径是否
  可辩护 —— 校准未通过前**不应**人工标注全部 60+40。
