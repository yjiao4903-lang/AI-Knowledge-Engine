# P8-BENCH-02 状态报告 · 盲化人工判定工具链 + auto_prelabel 更正（2026-09-11）

**Issue**：LOCAL-DEV #39（父控制 #30） ｜ **PR**：#41
**分支**：`local-dev/39-p8-benchmark-pilot`（基于权威 `main` `035ecccc`）
**执行者**：LOCAL-DEV

## 0. 结论（先行）

1. **撤回**上一版本报告"自动出题金标不可作为门线 / 检索质量无问题"的表述。2026-09-11
   WEB-CONTROL 更正（PR #41 REQUEST_CHANGES）指出：`p8_bench_pool.py::grade_chunk()` 用
   token 包含 + 正则谓词**机械**判定相关度，其产物是**机器预标注 `auto_prelabel`**，
   **不能**用来推断检索质量，也**不能**用来判定 benchmark 无效。上一版的
   "43/60、24/40 池内无 grade-3" 与 "Dev Hit@5 0.167" 因此只是"自动 rubric 与检索池不相交"
   的观察，不是效度结论。
2. 已按该更正重建证据链：新增**盲化人工相关性判定工具链**（`p8_bench_adjudicate.py`：
   export / import / report + `adjudication_schema_v1.json`），并把全部自动产物显式重分类为
   `auto_prelabel`。
3. **校准门线尚未完成**：`human_review_complete = false`。Dev 20 + sealed Holdout 10 的
   盲化人审包**已生成**，但**人工领域判定尚未录入**，因此
   "auto_prelabel vs 人工分歧" 与"人工 gold 重算指标"**暂无有效数字**。
4. Legacy 50 保持冻结（sha256 `aa0412a2…`），未改检索/权重/routing/reranker，未改语料与索引。

## 0b. 批次替换（2026-09-11 WEB-CONTROL 控制决定）

**v1 校准包已作废并从人工校准门线撤回。** 领域审阅者反馈：在未读过源报告时，多条 v1 query
无法被可复现地理解与判定 —— 它们依赖隐藏的源报告上下文（未定义的「报告中」「相关指标」
「数量上的差异」「作用」等）。因此审阅者只能猜测作者意图，该批次不是有效的人工判定输入。

**处置**：

- v1 Dev/Holdout 包迁入 `benchmark/adjudication/superseded/`（仓库外密封件同样迁入 `superseded/`）；
- 两个 v1 key 写入 `withdrawn` 标记；`p8_bench_adjudicate.py import` 对带该标记的批次**直接拒绝**
  （除非 `--allow-withdrawn`），因此 v1 **不可能**被计入 `human_review_complete`；
- 生成 **v2 替代批次**，且必须先过新增的 **Query Validity Gate**。

### Query Validity Gate（人审前置门，确定性预过滤）

一条 query 合格需同时满足：无未解析指代；显式命名 ≥1 实体（latin 专名或中文专名词表）与
≥1 具体化维度（营收/毛利率/价格/产能/capex/概率/机制/份额/风险…）；无泛化占位维度；含疑问标记。
仅作预过滤，权威判定为 WEB-CONTROL 对 Dev query 清单的 sanity review。

### v2 批次结果

| 项 | Development | sealed Holdout |
|---|---|---|
| 题数 | 20 | 10 |
| Query Validity Gate | **20/20 通过** | **10/10 通过** |
| 结构校验（tier 护栏 / OCR / 泄漏 / 密封 / Legacy） | pass（max tier 25%、min 10%、OCR 30%） | pass（max tier 20%、min 10%、OCR 30%） |
| tier 覆盖 | 6/6 | 6/6 |
| family 覆盖 | 6/6（max 25%） | 6/6（max 30%） |
| 盲化包 packet sha256 | `889d6ee0…` | `ddd81996…`（仓库外） |
| 人工判定 | 未录入（`human_review_complete=false`） | 未录入 |

出题方法：从**源 chunk 的真实主张**出发人工撰写 query（`authored_v2/development_authored_v2.jsonl`
记录每条题锚定的 chunk、实体、维度与期间），rubric 只用于 auto_prelabel 枚举候选金标。

**诊断（不作为调参依据）**：v2 池化后 Dev「4 视图 top-50 池内无 grade-3」由 v1 的 **43/60 降到 2/20**，
Holdout 为 **0/10**，FN 修正各 0。按 Issue #39，检索名次/分数**未**用于修改 query 措辞或检索参数，
该数字仅作诊断记录。

### Dev 20 query 清单

见 `benchmark/adjudication/query_validity_audit_v2.json` 的 `development.queries`；
按 WEB-CONTROL 要求，该清单已在提交人审前单独贴出供 sanity review。


## 0c. 人审包锚点修复（2026-09-12，WEB-CONTROL blocking review on `1f19765b`）

Dev20 人工审阅已录入（19 accept / DEV2-19 reject，`judgments_development_calibration_v2.jsonl`，
**provisional，不作为最终 benchmark 状态**）。审阅暴露一个方法学缺陷：

- **根因**：`export` 以四个冻结视图的并集构建候选行集，再用 `if c in rows` 过滤 auto-gold / FN；
  authored v2 的 `judging.meta.ground_chunk`（出题时冻结的 grade-3 源锚点）若未被任何视图召回，
  会被**静默丢出人审包**。
- **后果**：DEV2-19 的锚点不在包内 → 审阅者看不到直接答案候选 → 只能 `reject`。
  把有效题按 reject 排除会删除一次真实 retrieval miss（survivor bias），系统性抬高 Hit@K/MRR/NDCG。
- **修复**：新增 `select_judging_pool()`——authored anchor **无条件纳入 judging pool**（追加在去重集合
  末尾，不重排）；`export` 对锚点缺失/跨 split **直接 fail**（非 warning）；key 侧
  `authored_anchors` 记录 retrieval-miss 状态；blinded packet 仍不含 view/rank/score/prelabel；
  强制纳入**不计为 retrieval hit**（正式指标只按 `views_ranked` 计算）。

### Dev20 审计结果（`adjudication/development_calibration_v2/anchor_audit_v2r2.json`）

| 项 | 值 |
|---|---|
| total queries | 20 |
| 旧 packet 缺 authored anchor | **2/20**（DEV2-17、DEV2-19） |
| 新 packet 缺 authored anchor | **0/20** |
| 锚点被至少一个视图召回 | 18/20 |
| 锚点未被任何视图召回、强制纳入 judging pool | 2/20（DEV2-17、DEV2-19） |
| packet 实质变化（需重审） | **DEV2-17、DEV2-19** |
| 可原样复用既有 human judgment | **18 题** |
| 不可用判定 | 0 |

- DEV2-19 的旧 `reject` **原样保留**在 judgments 文件中用于审计，未被静默改成 accept；
  新包中其锚点为 `DEV2-19#c016`，需人类审阅者重判，LOCAL-DEV 不代判。
- 人审迁移由 `p8_bench_adjudicate.py migrate` 确定性完成（`migration_report_v2r2.json`）：
  query 未变 + cand_id→chunk 映射未变 + 候选集合未变 ⇒ 复用；否则 `needs_human_re_review`。
- `import` 增加**批次同源 fail-fast**：v2 judgments + v1 questions 已实测被拒（20 条错误），
  v2 + v2 通过校验；README/脚本文档中的 v2 import 示例已改为
  `adjudication/authored_v2/development_v2_frozen.jsonl`。
- packet 重新生成：`889d6ee0…` → `4cf9a91a…`（同路径覆盖，旧哈希记录于 audit / determinism check，
  Git history 可溯源）。
- 诊断（不在本轮修复范围）：另有 **10 个非锚点** auto_prelabel gold chunk（分布在 7 题，DEV2-06 占 6）
  未被任何视图召回、因此不在人审池。其偏差方向与锚点缺失**相反**（保守：把检索命中的相关块当不相关），
  是否扩展强制纳入范围由 WEB-CONTROL 决定。
- 未调 retrieval weights / routing / reranker；未改 query 文本、语料、Legacy 50；
  未进入 sealed Holdout 人审。


## 0d. Dev20 人工校准完成（2026-09-12）

WEB-CONTROL 已对重生成 packet（r2）上仅变化的两题（DEV2-17、DEV2-19）完成人工确认
（其余 18 题按 `migration_report_v2r2.json` 原样复用）。执行 `import --require-complete`：

- **pass**；20 条判定全部 accept；`candidate_completeness` coverage **1.0**；
  **`human_review_complete = true`**；
- 人审后 FN 审计：20 题均新增了人审判为相关而预标注金标未收录的块，共 **112** 个 chunk 补入 gold；
  每题 grade≥2 相关数中位 **7**。

### Development human-gold 检索指标（hybrid_rerank 生产臂，检索行为未改）

| Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | Recall@5 | Recall@10 |
|---|---|---|---|---|---|---|
| 0.800 | 0.950 | **1.000** | 0.877 | 0.857 | 0.440 | 0.552 |

buckets：OK = 20/20。auto-vs-human 分歧与人审池 recall 见
`adjudication/adjudication_report_v2.json` / `.md`；trace 在密封工作区
`E:/研报提取资料库/_golden/p8_experiments/p8_bench02_dev_human_v2/`。

> 口径提示：gold 为人审后的有界池分级相关集（标准 pooling 假设），非全语料穷举；
> 与 Legacy 50 / v1 auto_prelabel 数字不可直接互比。本轮**不据此调整任何检索参数**。


## 1. 证据分级（本报告所有数字的引用前提）

| 证据类别 | 来源 | 可否用于效度/检索质量结论 |
|---|---|---|
| `auto_prelabel` | `p8_bench_pool.py::grade_chunk()`（token 包含 + 正则谓词） | **否** |
| `agent_assisted` | 模型/工具辅助判定 | 否（仅流水线验证/参考） |
| `selftest` | 工具链 plumbing 自检的合成判定 | 否（严禁引用） |
| `human` | 人类领域审阅者判定 | 是，且必须覆盖全部校准题 |

`import` 的 freeze 文件中 `human_review_complete` 只有在**全部校准题均为 `human` 且无缺题**时才为 `true`。

## 2. 本次交付物

| 产物 | 说明 |
|---|---|
| `docs/p8_review/scripts/p8_bench_adjudicate.py` | 盲化人审包 export / 判定 import / 分歧 report + 无 GPU `self-test`（14 项检查）。 |
| `docs/p8_review/scripts/p8_bench_views.py` | 四个冻结检索视图的**单一实现**，pool 与人审包共用，避免两者候选集漂移。 |
| `docs/p8_review/benchmark/adjudication/adjudication_schema_v1.json` | 判定记录 schema：grade 0–3、accept/rewrite/reject/ambiguous、审阅人/版本/时间戳、证据分级与密封规则。 |
| `docs/p8_review/benchmark/adjudication/README.md` | 工作流、盲化保证、命令、已披露限制。 |
| `.../adjudication/development_calibration_v1/` | Dev 20 题盲化人审包（packet / manifest / review_form / judgments 模板）。 |
| `.../adjudication/_keys/key_development_calibration_v1.json` | Dev 盲化映射（cand_id → chunk_id / 视图名次 / 预标注 grade）。 |
| `.../adjudication/determinism_check_v1.json` | 可复现性证据（见 §4）。 |
| sealed Holdout 10 题人审包 + key | **仓库外密封**（`E:\研报提取资料库\_golden\p8_bench02_adjudication\`）。 |
| `pilot_manifest_v1.json` | 标注 `evidence_class = auto_prelabel` + adjudication 区块与阻塞项。 |
| `development_v1/pilot_v1_auto_prelabel.jsonl` | 原 `pilot_v1_machine_not_gate.jsonl` **改名**（内容未变，sha256 `8f0ce5d5…`）。 |

## 3. 校准门线状态（Issue #39 要求：Dev 20 + sealed Holdout 10）

| 项 | 状态 |
|---|---|
| 盲化人审包生成（20 Dev / 10 sealed Holdout） | ✅ 完成，按 tier 轮转 + family 覆盖确定性抽样 |
| 盲化（隐藏视图/名次/分数/预标注 grade） | ✅ 包内不含；映射单存 key；Holdout key 在仓库外 |
| 判定 import schema 校验 | ✅ 完成（自检 24/24） |
| **candidate-level completeness 门** | ✅ 完成：`accept`/`rewrite` 必须对该题人审包内**每个候选**判定且仅判定一次；缺候选 / 未知候选 / 重复候选一律拒绝导入；freeze 与 report 均输出 `candidate_completeness`（逐题 `graded` vs `packet`），未达 100% 时 `human_review_complete=false` |
| reject / ambiguous 的指标排除 | ✅ 完成：题目级处置，不要求逐候选判定，但在 `excluded_from_metrics` 中逐题列出并完全排除出 gold 与指标 |
| 人工判定录入 | ❌ **未完成** —— 需人类领域审阅者填写 |
| 只由人工 grade 重算 gold | ⏸ 待人工判定后执行 |
| 人工判定后的 FN 审计 | ⏸ 同上（机制已就绪：`judging.fn_added_after_human_audit`） |
| auto_prelabel vs 人工分歧 | ⏸ 暂无有效数字 |
| 由人工 gold 重算指标 | ⏸ 命令已就绪（`p8_trace.py --questions <gold.jsonl>`） |

**阻塞原因**：LOCAL-DEV 是本地自动化执行者，不能替代人类领域判定。人审包、schema、导入器与
分歧报告器均已就绪；录入判定后 `import` → `report` 即可产出人工 gold、分歧指标与 freeze 哈希。

## 4. 可复现性与确定性证据（`determinism_check_v1.json`）

`p8_bench_pool.py` 已重构为共用 `p8_bench_views.py::FrozenViews`（行为等价），重新执行验证：

| 检查 | 结果 |
|---|---|
| 出题器重跑（Dev/Holdout） | 原始 sha256 `80be7fc8…` / `fa5040d0…`，与既有构建一致 |
| Dev 池化重跑 vs 已提交冻结件 | **逐字节一致**（`4a5e50b5…`） |
| Dev 池化审计摘要 | 除耗时外完全一致（fn 2、无 grade-3 43/60、池中位 101） |
| Holdout 池化重跑 | 冻结件 sha256 = `7a61cc07…`，**与 manifest 记录一致**（恢复密封件） |
| 结构校验 `p8_bench_verify.py` | pass（Dev 60 / Holdout 40、tier 护栏、泄漏 0、密封、Legacy 冻结） |
| 判定工具链 `self-test` | **24/24 通过**（含缺候选 / 部分候选 / 重复候选 / 完整度标志 / reject 指标排除） |
| plumbing dry-run（真实 Dev 包 import→report） | exit 0；7 题 accept 候选覆盖 100%，13 题 reject 被 `excluded_from_metrics` 排除；产物未入库、合成 grade 不作为证据 |
| 反向验证：从某个 accept 题删掉 1 个候选 | `import` **exit 1**，报「候选判定不完整 —— 该题人审包共 20 个候选，缺 1 个」 |

## 5. 保留的 auto_prelabel 观察（仅作可复现记录，**不可**引用为效度结论）

池 = 4 冻结视图（lexical / dense / hybrid / hybrid+rerank）各 top-50 的并集，池大小中位 101：

- 预标注相关的池内块数中位 **0**；池内无 grade-3：Dev **43/60**、Holdout **24/40**；
- FN 审计（预标注口径）：Dev 2 / Holdout 3；
- 冻结预标注 gold 上的指标：Dev Hit@5 **0.167**、Holdout **0.200**、Legacy canary **0.820**
  （`self_check_pass=true`）。

> 上述数字**只能**说明 `grade_chunk()` 的机械规则与检索池几乎不相交，属于**预标注质量问题**；
> 在人工判定完成前，**不得**据此断言 benchmark 无效或检索质量差。

## 6. PR #41 审查清单逐条状态

| # | WEB-CONTROL 要求 | 状态 |
|---|---|---|
| 1 | 把自动产物重分类为 `auto_prelabel` / candidate bootstrap | ✅ manifest + 文件改名 + README + 报告 |
| 2 | 确定性盲化判定包 export（隐藏视图/名次/分数） | ✅ `export` + 双 split 包 |
| 3 | 判定 import/schema（grade 0–3、状态、审阅人、时间戳、freeze 哈希；Holdout 不入库） | ✅ `import` + schema + 密封护栏 |
| 3b | **candidate-level completeness**：accept/rewrite 必须逐候选判定；缺/未知/重复候选拒绝；freeze/report 暴露完整度计数；未达 100% 不得 `human_review_complete=true`；reject/ambiguous 可题目级但须显式排除出指标 | ✅ 已修复（对应 2026-09-11 追加 review） |
| 4 | 先做 20 Dev + 10 sealed Holdout 人工校准门线 | ✅ v2 包已生成（跨 6 tier / 6 family），先过 Query Validity Gate 20/20 + 10/10 |
| 5 | 对 30 题做人工领域判定；只用人工 grade 重算 gold；人审 FN 审计；报告 auto vs 人工分歧 | ❌ **阻塞：需人类判定**（机制全部就绪） |
| 6 | 不据自动 rubric 推断检索质量/benchmark 无效；Legacy 冻结；不改检索 | ✅ 报告已撤回相关结论；Legacy `aa0412a2…` 未变 |
| 7 | 新 head SHA + CI 证据 + 校准产物/聚合 + 报告分离两类证据 | ✅ 见 PR 说明（第 5 项的聚合待人工判定） |

## 7. 边界与未做

- 未发布 150+150；未把本试点作为门线；未改检索权重/routing/reranker；未改 Legacy 金标；
- 未做语料重写/重抽取/重索引；Holdout 题目/金标/逐题判定/key 均未入库；
- `配图资料` 仍为 `（未 OCR）` 占位，未伪造 OCR 金标（记为语料质量限制）；
- 未将任何 `agent_assisted` / `selftest` 判定当作人工证据；本地无关改动
  `config/config.yaml`、`docker-compose.yml` 未纳入提交。

## 8. 复现命令

```bat
:: 结构校验
.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_verify.py ^
  --development docs\p8_review\benchmark\development_v1\pilot_v1_auto_prelabel.jsonl ^
  --holdout "E:\研报提取资料库\_golden\p8_bench02_adjudication\holdout_frozen_v1.jsonl" ^
  --out docs\p8_review\benchmark\pilot_verification_v1.json ^
  --md docs\p8_review\benchmark\pilot_coverage_v1.md

:: 判定工具链自检（无 GPU）
.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py self-test

:: 重新生成人审包（Dev）
.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_adjudicate.py export ^
  --questions docs\p8_review\benchmark\development_v1\pilot_v1_auto_prelabel.jsonl ^
  --split development --n 20 ^
  --outdir docs\p8_review\benchmark\adjudication\development_calibration_v1 ^
  --keydir docs\p8_review\benchmark\adjudication\_keys ^
  --pool-audit docs\p8_review\benchmark\development_v1\pool_audit_v1.json
```
