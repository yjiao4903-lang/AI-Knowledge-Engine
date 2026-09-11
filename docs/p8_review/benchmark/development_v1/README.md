# Development Benchmark v1（结构与规范；题集待出）

> **2026-09-11 P8-BENCH-02 证据分级更正（WEB-CONTROL / PR #41）**：本目录
> `pilot_v1_auto_prelabel.jsonl`（原名 `pilot_v1_machine_not_gate.jsonl`，内容未变，
> sha256 `8f0ce5d5…`）是 #39 的 60 题 claim/context-specific 试点，其 gold 全部由
> `p8_bench_pool.py::grade_chunk()` 的 **token 包含 / 正则谓词机械预标注**生成
> （`evidence_class = auto_prelabel`），**不是人工相关性判定**。
>
> 因此此前据它得出的"4 视图 top-50 池内 43/60 题无 grade-3、Dev Hit@5 0.167"只能说明
> **自动 rubric 与检索池不相交**，**不能**用来推断检索质量或判定 benchmark 无效。
> 人工判定走 `../adjudication/`（盲化人审包 + `p8_bench_adjudicate.py`）；
> 当前人工校准门线**未完成**。详见 `../reports/P8_BENCH02_STATUS_20260911.md`。

> **2026-09-11 P8-BENCH-01 状态（重要）**：本目录的
> `candidates_v0_machine_review_only.jsonl` 是**机器生成的候选集，仅供复核，不是正式门线题集**。
> 它 150 题、schema 校验通过、`unresolved=0`、无 Dev/Holdout 泄漏，但**金标不可辩护**：
> 锚点词在语料中位出现于 ~290 篇文档 / ~1018 chunks，单 chunk 金标对宽泛实体查询不是公平
> 相关性目标；同引擎 Legacy canary 复现 Hit@5 0.82，而本候选集 Hit@5 仅 0.10。
> 详见 `../reports/P8_BENCH01_STATUS_20260911.md`。**正式 Development 150 仍需人工领域出题**
> （本目录规范与工具可直接复用）。

**用途**（规范 §5.2）：参数实验、失败归因、routing 设计。允许随 P8 早期发现有限修订，**每次修订必须有版本号**（`version` 字段，文件另存 `questions_v1.jsonl` → `questions_v2.jsonl`）。

**规模建议**：100–150 题（规范）；交接建议**先出 30–50 题即可支撑后续实验**（P8-1 是关键路径上最长的杆）。

**split 值**：`development`

## 题型覆盖（规范 §5.3，不得随机抽题）

| query_type | 说明 | 建议题量 |
|---|---|---|
| exact_entity | 公司/产品/人物/指标 | ≥10 |
| exact_number | 数值/日期/比例 | ≥10 |
| semantic_thesis | 观点/逻辑/结论 | ≥15 |
| causal | 因果链条 | ≥10 |
| temporal | 某阶段发生了什么 | ≥8 |
| long_tail | 低频主题 | ≥8 |
| cross_doc | 多文档共同支持 | ≥8 |

同时按 `source_type` 覆盖：`flagship`（旗舰）/ `formal_report`（外资研报）/ `daily`（日报/交易台）/ `discussion`（即时讨论）/ `image_material`（配图 OCR）；另设 `bilingual` 标注位。

## 金标锚定（强制）

**禁止 `heading_contains`**。必须使用 `gold.chunks = [{chunk_id, grade}]`；若难以直接取 chunk_id，可用 `gold.content_anchors`（正文唯一片段）辅助定位，但**落盘前必须解析为 chunk_id 并校验 `unresolved = 0`**。

理由见 `../legacy_v1/README.md` 与 `P8_新窗口交接说明_20260911.md` §8.1。

## 校验

```bat
D:\AI-Knowledge-Engine\.venv\Scripts\python.exe pipeline\p8_bench_validate.py ^
  --questions _golden\benchmark\development_v1\questions_v1.jsonl --split development
```

校验项：schema 必填字段、split 值、gold 可解析、`unresolved=0`、grade>=2 非空、id 唯一、禁止 heading 锚定。

## 出题工作流（半自动）

1. 人（领域判断）：选题 → 写 query → 指定目标文档/章节范围 → 给 grade；
2. 工具（自动）：`p8_bench_validate.py --suggest-chunks --doc <doc_id> --section <section_id>` 列出候选 chunk_id 供人工选定；
3. 工具（自动）：写回 `chunk_id` 并复校验 `unresolved=0`；
4. 落盘 `questions_v<n>.jsonl` + `_meta/p8_decisions.md` 记录修订理由。

> 题集本身**需要用户领域判断**（交接说明 §9.2），本窗口只交付结构、规范与校验/候选工具，不代拟题目。
