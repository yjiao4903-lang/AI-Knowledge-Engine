# L1A TaskPack Smoke & External Run Guide

> 日期：2026-08-30 ｜ 依据：V3.0 §72/§73（Task 8/9）｜ 使用者：用户（本指引不调用模型）
> **当前状态：准备包，未宣称 Task 9/10 完成。** 本指南只定义可判定的 smoke 流程；外部 Worker 执行模型，KE 只生成/校验 TaskPack。
>
> 当前仓库已提交 Schema/Builder/模板，Importer/API/测试仍可能处于工作区变更状态；“实现具备”不等于 smoke 已通过。执行前必须以当前 `git status`、测试和真实 API 响应为准。

---

## 0. 前置：启动环境

```bash
# 1) 核验/（必要时幂等）构建黄金 TaskPack；当前工作区已包含脚本和 32 个输入包
cd D:\AI-Knowledge-Engine
.venv\Scripts\python.exe backend\scripts\migrate_golden_taskpacks.py

# 2) 启动 KE（供 Task Center / Importer / Watcher）
cd D:\AI-Knowledge-Engine\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
# 3) 启动前端
cd D:\AI-Knowledge-Engine\frontend
& D:\AI-Knowledge-Engine\.tools\node\npm.cmd run dev   # http://127.0.0.1:5173/tasks
```

## 1. 四个 smoke 任务定义（每类 1 个）

在 Task Center（`/tasks`）逐一点「创建 TaskPack」，或直接调用 API：

```bash
# 四类各 1：可从 data/taskpack_golden/task_001|009|018|025 的 query/evidence 复制（summary/comparison/causal/tension）
POST /api/synthesis/tasks   # body= {task_type, query, evidence_refs}
```

以下是验收所需四类任务。当前已核实 `data/taskpack_golden/task_001..032/` 共 32 个输入包，以及 `backend/scripts/migrate_golden_taskpacks.py`、`backend/scripts/taskpack_eval.py` 均存在；这些是静态/文件存在事实，不代表外部 Worker 已运行。

| smoke | task_type | 参考 golden 包 |
|---|---|---|
| 1 | summary | task_001（HBM4 位宽演进） |
| 2 | comparison | task_009（单相 vs 两相浸没式） |
| 3 | causal_synthesis | task_018（AI 算力→液冷因果） |
| 4 | tension_extraction | task_025（封装价值提升 vs 供应链瓶颈张力） |

### 当前 R1 / R2 口径

外部 4-task smoke 的机器 Gate 可记为 **R1：机器通过、语义需修订**：至少复核 task_001 的 HBM4E 2027E 预测、task_018 的 Rubin 1,800W+预测/因果链、task_025 的 CoWoS/HBM 行业预测，不得仅凭 4/4 机器 Gate 宣称语义通过。完成正典 Prompt 修订后，**R2 才是重跑候选**；R2 必须使用新模板重新生成/复制任务包并执行外部 Worker，不能直接复用旧结果。

## 2. 在外部工具中执行（Task 8 验证完整链路）

对每个任务：

1. Task Center 打开任务目录（「打开目录」）→ 复制「启动提示词」。
2. 在 Trae / Codex / Qwen Code / Claude Code 打开任务目录，把 AGENT_INSTRUCTION_V1.md 作为指令粘贴。
3. 让工具读取 `evidence.jsonl`，调用你选定的模型，生成 `result/result.json` + `run_meta.json`。
4. 只在 `result.json`、`run_meta.json` 写完并自检后，将任务目录移到配置的 `taskpack.root_dir/completed/<task_id>/`；当前默认根目录是 `D:\AI知识整合体系\taskpacks`。最后创建 `result/DONE`。

预期状态流转：Create（READY）→ 外部 Agent（可在 processing）→ `result/DONE` → Watcher/rescan → 八步 Gate → COMPLETED；用户明确接收 Viewer 后才可写 `result/IMPORTED` → IMPORTED。失败写 FAILED 或 INVALID_RESULT，不能创建 DONE。

## 3. 校验（无模型）

```bash
# 八步 Gate / API rescan：直接调用端点；Task Center 只有在当前前端确实提供 `/tasks` 时才使用
POST /api/synthesis/tasks/<id>/rescan

# 批量无模型评估（把 runs 结果放 data/taskpack_golden/runs/<worker>/）
cd D:\AI-Knowledge-Engine
.venv\Scripts\python.exe backend\scripts\taskpack_eval.py --runs runs/<worker>
```

## 4. 32 Golden External Run（Task 9）

- 从 Task Center 或直接复制 `data/taskpack_golden/task_001..032/` 逐个执行。
- **至少记录**：`worker_tool` / `model` / `prompt_sha` / `result`（V3.0 §73）。
- 建议按批次执行；结果统一放 `data/taskpack_golden/runs/<worker>/task_NNN/result/result.json`。
- 记录在 `L1A_TASKPACK_EVALUATION.md` 或本文件追加。

## 5. Task 10 评估

执行 `taskpack_eval.py --runs data/taskpack_golden/runs/<worker>` 核对硬 Gate（§74），并按 Entailment 审核表人工标注（≥90%）与终审 Critical Contradiction = 0。当前 `data/taskpack_golden/runs/` 为空，因此 Task 9/10 仍只能记为 `blocked`，不能记为 PASS。

## 6. 完成后

只有 4-task smoke 全部通过、32 条 Task 9 外部结果齐全、Task 10 硬 Gate 和人工 Gate 均有记录后，才能把结果写入 `L1A_TASKPACK_EVALUATION.md`。在此之前应保留 `准备中/blocked`。V3.0 §76：**不进入 L1B**（不自动开发 LLM 自主检索 / Agent 自动研究 / Draft→Proposal / MCP）。

## 7. 机器可判定验收清单

逐项记录 `PASS` / `FAIL` / `blocked`，并附响应或文件路径；未执行不得填 PASS。

```text
[ ] 创建返回 HTTP 200，status=READY，task_path 位于配置 root/outbox/<task_id>
[ ] 包内 task.yaml / AGENT_INSTRUCTION.md / evidence.jsonl / output_schema.json / README.md / manifest.json 全部存在
[ ] manifest.files 每项 SHA-256 重算一致，evidence_count 与行数一致
[ ] Worker 只写 result/；result.json、run_meta.json 完整且 schema 可解析
[ ] DONE 最后创建；无 DONE 时 importer 不读取半成品
[ ] Gate 1 manifest 通过
[ ] Gate 2 result_schema 通过
[ ] Gate 3 task_id 一致
[ ] Gate 4 prompt_sha 与 task manifest SHA 一致
[ ] Gate 5 evidence_membership 通过
[ ] Gate 6 citation_invalid = 0
[ ] Gate 7 citation_coverage >= 0.95
[ ] Gate 8 unsupported_claim <= 0.05
[ ] stale 已检测并记录；不自动改写 TaskPack
[ ] 全 Gate 通过后为 COMPLETED；用户明确接收后才写 IMPORTED
[ ] 任一 Gate 失败为 INVALID_RESULT，并有 result/INVALID 与失败 Gate
[ ] Worker 失败为 FAILED，并有 error.json + FAILED，不能有 DONE
[ ] archive API 后为 ARCHIVED，目录位于 root/archive/
[ ] 无任何路径把 result 直接写入 Cognition 正式库；无自动 Proposal/认知晋升
```

责任边界：外部 Worker 负责包内读取、结果三件套和 marker；KE 负责 Builder、Importer、Gate 和状态；主负责人负责证据审查、人工 Entailment/Contradiction 判定及最终 PASS；用户只在明确查看/接收后触发 IMPORTED。
