# P8-BENCH-02 状态报告 · human-in-the-loop 试点（60 Dev + 40 sealed Holdout，2026-09-11）

**Issue**：LOCAL-DEV #39（父控制 #30）
**分支**：`local-dev/39-p8-benchmark-pilot`（基于权威 `main` `035ecccc`）
**执行者**：LOCAL-DEV

## 0. 结论（先行）

已按 #39 规范实现并跑通 **claim/context-specific 出题 + 多 chunk 分级金标 + 4 视图 pooled judging +
false-negative 审计**的完整工具链，并产出结构上合格的 60 + 40 试点题集（全部护栏通过）。
但**评测证明该自动出题的金标仍不可作为检索门线**，故按 #39 的止损条款
（"or a smaller defensible set with an explicit limiting-factor report"）**不将其发布为正式 benchmark**。

**限定因素**：即使金标已改为"同实体+同数值"的有界多 chunk 集合，**4 个冻结检索视图 top-50 的并集**中，
dev 有 **43/60**、holdout 有 **24/40** 的题**完全不含任何 grade-3 相关块**；语料中确实存在这些正例，
但系统（以及任何真实查询）没有任何信号把它们排上来。即：自动抽取的"实体+数值共现"金标与
**可检索的信息需求**不对齐。Dev 试点 Hit@5 0.167、Holdout 0.200，而 Legacy canary 0.82
（`self_check_pass=true`）——引擎健康，差距来自基准效度，不是检索质量。

## 1. 与 #36 的改进（本次实际做到的）

| 维度 | #36 | #39 本试点 |
|---|---|---|
| 查询 | 宽泛实体提示（"报告中 X 怎么样"） | claim/context-specific，≥2 判别项（实体+指标/期间/第二实体+因果谓词） |
| 金标 | 单一任意 chunk | 有界多 chunk，grade 3/2，rubric 显式（req/broad2/谓词），中位 2 个正例、max 10 |
| 判定 | 无 | 4 冻结视图（lexical/dense/hybrid/hybrid+rerank）top-50 建池 + rubric 判定 + FN 审计 |
| 泄漏 | 未涉及 | 金标限定在本 split 文档集内，Dev∩Holdout 目标文档 overlap = 0 |

结构性指标显著改善（#36 金标中位 1018 chunk → 本试点中位 2 个正例），但**效度**仍不过关。

## 2. 交付物

| 产物 | 说明 |
|---|---|
| `docs/p8_review/scripts/p8_bench_pilot_build.py` | 确定性出题：claim/context-specific 家族（numeric/comparison/mechanism/temporal/entity_context/multi_evidence），rubric 化多 chunk 金标，tier/family 配额与护栏。 |
| `docs/p8_review/scripts/p8_bench_pool.py` | 4 冻结视图 top-50 建池 → rubric 判定 → FN 审计 → split 限域金标 → 生成冻结题集。不修改任何检索参数。 |
| `docs/p8_review/scripts/p8_bench_verify.py` | 扩展支持 rubric 金标：grade3 必须满足 req/谓词、grade2 满足 broad2；source hash 冻结、泄漏、密封、Legacy 冻结校验。 |
| `docs/p8_review/benchmark/pilot_manifest_v1.json` | 试点 freeze manifest（seed、配额、组成、SHA256、pool 审计摘要、限定因素）。 |
| `docs/p8_review/benchmark/development_v1/pilot_v1_machine_not_gate.jsonl` | Development 60（**明确标注非门线**）。 |
| `docs/p8_review/benchmark/development_v1/pool_audit_v1.json` | Dev pooled judging 审计（逐题池大小/相关数/FN）。 |
| `docs/p8_review/benchmark/pilot_verification_v1.json` / `pilot_coverage_v1.md` | 结构校验与覆盖表。 |
| sealed Holdout 40 | 本地密封（仓库外），仅 manifest 中落 SHA256 与聚合组成/指标。 |

## 3. 结构校验（全部通过）

- Dev = 60，sealed Holdout = 40；schema/枚举/唯一 id 通过，**每题 ≥1 grade-3**；
- 分层护栏：dev max tier 35% / min 10%；holdout max 35% / min 10%；family max dev 28.3% / holdout 35%；
- OCR-derived：dev 18.3% / holdout 17.5%（≥10%）；
- 泛化实体提示：0%（全部为 claim/context-specific，scoped 诊断子集 0 ≤ 20%）；
- Dev∩Holdout 目标文档 overlap = 0；九个 Legacy target 文档未用作 gold；
- source hash 与当前 catalog 一致（源未漂移）；Holdout 在仓库外（密封）；
- Legacy 50 sha256 `aa0412a2…` 未变；
- 相关度分布：正例中位 2（max 10），grade-3 中位 2（max 6）。

## 4. 试点评测（检索代码/权重/routing/reranker 未改）

| 题集 | n | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p95(ms) |
|---|---|---|---|---|---|---|---|
| Legacy 50 canary（冻结） | 50 | 0.520 | 0.720 | **0.820** | 0.640 | 0.678 | 1295 |
| Development 60（本试点） | 60 | 0.100 | 0.133 | **0.167** | 0.133 | 0.161 | 1003 |
| sealed Holdout 40（仅聚合） | 40 | 0.125 | 0.175 | **0.200** | 0.156 | 0.166 | 1082 |

Wilson 95% CI（hit 率）：Dev Hit@5 [0.093, 0.280]；Holdout Hit@5 [0.105, 0.348]；Legacy Hit@5 [0.692, 0.902]。
Holdout 逐题 trace 仅存本地密封路径，未进入仓库。

## 5. 关键证据：pooled 候选池几乎不含金标

- 每池 = 4 视图（lexical / dense / hybrid / hybrid+rerank）各 top-50 的并集，池大小中位 **101**；
- 池中 rubric 相关（grade≥2）块数中位 **0**；
- **无任何池内 grade-3 的题**：Dev **43/60**、Holdout **24/40**；
- FN 审计：仅 2（dev）/ 3（holdout）处池内相关但未标注，已在 freeze 前补入——即池内几乎没有"漏标"，
  问题是**相关块根本不在池里**；
- 逐题诊断（`pool_audit_v1.json`）显示 `pooled_relevant=0` 是常态。

这说明：以"实体+数值共现"定义的金标，其正例在 296k chunk 全库中广泛存在，但检索视图无法把它们
排在 top-50——因为查询本身（"X 的 revenue 是多少"）没有指向该数值片段的信号。该基准的
**信息需求—金标对齐**不成立，低分不能被解释为"检索质量差"。

## 6. 为什么自动出题仍达不到门线质量

要构成可辩护的检索题，需要领域判断同时做到：
1. 查询指向**一个具体、可检索**的信息需求（具体主张/结论，而非"实体+数值"共现）；
2. 金标为该需求下**系统可能返回**的相关集合，并明确穷尽边界。

自动管线只能保证"金标确实含有答案 token"，无法保证"该信息需求会被任何排序器视为目标"。
本任务名为 human-in-the-loop，但 LOCAL-DEV 是本地自动执行者；**缺失的正是人类领域出题/判定这一环**。

## 7. 建议下一步（需 WEB-CONTROL / 用户决策）

1. **人工出题 + 工具辅助判定**：由领域出题人写 60/40 题（每条指定报告/主题与具体主张），
   工具执行池构建、rubric 判定、FN 审计、冻结与校验（本 PR 已交付该工具链）。
2. 或**改为"指定报告范围的检索"**基准：query 显式命名报告/主题，金标为该范围内的相关块，
   使信息需求可检索——属题集设计变更，需 #30 决策。
3. 不建议在本试点上继续调检索参数：金标未达门线效度。

## 8. 边界与未做

- 未发布 150+150；未把本试点作为门线；未改检索权重/routing/reranker；未改 Legacy 金标；
- 未做语料重写/重抽取/重索引；Holdout 逐题 trace 未入库；
- `配图资料` 仍为 `（未 OCR）` 占位，未伪造 OCR 金标（记为语料质量限制）；
- 本地无关改动 `config/config.yaml`、`docker-compose.yml` 未纳入提交。

## 9. 复现

```bat
:: 出题
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_pilot_build.py ^
  --split development --outdir <dir> --manifest <manifest.json>
:: 池化判定 + FN 审计（需 GPU / Qdrant 16333）
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_pool.py ^
  --questions <questions.jsonl> --split development --topn 50 --out <audit.json> --corrected <frozen.jsonl>
:: 结构校验
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe docs\p8_review\scripts\p8_bench_verify.py ^
  --development <dev.jsonl> --holdout <sealed.jsonl> --out <verify.json>
:: 评测（E 盘工作区）
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe pipeline\p8_trace.py --exp p8_bench02_dev ^
  --questions <dev.jsonl> --split development
```
