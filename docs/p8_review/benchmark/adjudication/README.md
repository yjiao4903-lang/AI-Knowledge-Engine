# P8-BENCH-02 盲化人工相关性判定（blinded human adjudication）

> **状态（2026-09-11）**：工具链已交付并通过无 GPU 自检；**Dev 20 + sealed Holdout 10 校准包已生成**。
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

## 工作流

```
export  →  人工判定（盲化）  →  import（只由人工 grade 重算 gold）  →  report（auto vs 人工分歧）
```

### 1. export：生成盲化人审包

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py export ^
  --questions docs\p8_review\benchmark\development_v1\pilot_v1_auto_prelabel.jsonl ^
  --split development --n 20 ^
  --outdir docs\p8_review\benchmark\adjudication\development_calibration_v1 ^
  --keydir docs\p8_review\benchmark\adjudication\_keys ^
  --pool-audit docs\p8_review\benchmark\development_v1\pool_audit_v1.json
```

产出（Dev 版本入库）：

| 文件 | 用途 |
|---|---|
| `packet_<split>_calibration_v1.jsonl` | 机器可读人审包：冻结 query + 打散候选 + 源文本 |
| `packet_<split>_calibration_v1.manifest.json` | 抽样/盲化/池化参数 + SHA256 |
| `review_form_<split>_calibration_v1.md` | 人读审阅表（粘贴/填表用） |
| `judgments_<split>_calibration_v1.template.jsonl` | 判定录入模板（已预置 cand_id 与 `grade: null`） |
| `_keys/key_<split>_calibration_v1.json` | **盲化映射**（cand_id → chunk_id / 视图名次 / 预标注 grade） |

盲化保证：包内**不含**检索视图归属、视图内名次、融合分数、`auto_prelabel` grade；候选顺序按
`random.Random("<seed>|<qid>|shuffle")` 确定性打散，`cand_id` 为打散后位置，不携带名次信息。

> 审阅人只看 `review_form_*.md` 或 `packet_*.jsonl`，**不要打开 `_keys/`**，否则盲化失效。

### 2. 人工判定

按 `adjudication_schema_v1.json` 填写 `judgments_*.template.jsonl`：

- `status`：`accept` / `rewrite` / `reject` / `ambiguous`；
- `grades[].grade`：0/1/2/3（3=直接回答，2=实质支撑，1=主题相关但不足，0=无关）；
- `accept` / `rewrite` 的题必须至少 1 个 grade-3；`rewrite` 必须填 `final_query`；
- 填 `reviewer` / `reviewer_kind: human` / `reviewer_version` / `reviewed_at`（ISO8601）。

### 3. import：只由人工 grade 重算 gold

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py import ^
  --judgments <filled.jsonl> --key docs\p8_review\benchmark\adjudication\_keys\key_development_calibration_v1.json ^
  --questions docs\p8_review\benchmark\development_v1\pilot_v1_auto_prelabel.jsonl ^
  --split development --require-complete ^
  --adjudication-out <adj.jsonl> --gold-out <gold.jsonl> --freeze-out <freeze.json>
```

- gold **只**由人工 grade ≥2 生成（`evidence_class = human_adjudicated`）；
- 同时做人工判定后的 false-negative 审计，把"人工判为相关但预标注 gold 未收录"的块记入
  `judging.fn_added_after_human_audit`；
- `reject` / `ambiguous` 的题排除出 gold 并单独记录；
- `--split holdout` 时若输出路径位于仓库内会**直接拒绝执行**（密封条款）。

### 4. report：auto_prelabel vs 人工分歧

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py report ^
  --judgments <adj.jsonl> --key <key.json> --split development --out <report.json> --md <report.md>
```

输出：candidate 级 grade 完全一致率 / ±1 一致率、二值相关（≥2）precision/recall/F1、
grade-3 集合 Jaccard、人工相关但预标注漏收的块数、以及人审池内的 benchmark-side recall。

正式指标仍由既有评测器在**人工 gold** 上重算（不改检索行为）：

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_trace.py ^
  --exp p8_bench02_development_human --questions <gold.jsonl> --split development
```

## 确定性自检（无 GPU）

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py self-test
```

覆盖：schema 拒绝（未知 cand_id / 非法 grade / accept 无 grade-3 / rewrite 缺 final_query /
缺 reviewer）、gold 往返只取人工 grade、FN 补入、freeze 哈希稳定、reject 不入 gold、
Holdout 密封护栏、抽样确定性、family 覆盖。当前 **14/14 通过**。

## 已披露限制

- **有界池**：候选为 4 个冻结视图 top-N 的有界轮转抽样（Dev 每题的候选上限 20），未出现在包内的块
  按不相关计（标准 pooling 假设）。因此本校准**不是**全语料穷举的完整相关性集合。
- **跨 split 排除**：池内属于另一 split 的候选被排除（Anti-leakage），数量记录在包的 manifest
  `selection.cross_split_candidates_excluded`。
- **校准子集**：`--n` 为校准规模（Dev 20 / Holdout 10），用于在扩展到 60+40 之前验证判定口径是否
  可辩护 —— 校准未通过前**不应**人工标注全部 60+40。
