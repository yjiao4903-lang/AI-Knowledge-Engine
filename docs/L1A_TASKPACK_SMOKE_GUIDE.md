# L1A TaskPack Smoke & External Run Guide

> 日期：2026-08-30 ｜ 依据：V3.0 §72/§73（Task 8/9）｜ 使用者：用户（本指引不调用模型）
> 开发侧已完成到 Task 8 架构、Task 11 文档；**Task 8 External Worker Smoke 与 Task 9 32 Golden External Run 由你在外部工具执行**。

---

## 0. 前置：启动环境

```bash
# 1) 构建黄金 TaskPack（幂等；依赖 KE catalog_full.db 与 32 条 golden 源）
cd D:\AI-Knowledge-Engine
.venv\Scripts\python.exe backend\scripts\migrate_golden_taskpacks.py

# 2) 启动 KE（供 Task Center / Importer / Watcher）
cd D:\AI-Knowledge-Engine\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
# 3) 启动前端
cd D:\AI-Knowledge-Engine\frontend
& D:\AI-Knowledge-Engine\.tools\node\npm.cmd run dev   # http://127.0.0.1:5173/tasks
```

## 1. 创建 4 个 smoke 任务（Task 8：summary / comparison / causal / tension 各 1）

在 Task Center（`/tasks`）逐一点「创建 TaskPack」，或直接调用 API：

```bash
# 四类各 1：可从 data/taskpack_golden/task_001|009|018|025 的 query/evidence 复制（summary/comparison/causal/tension）
POST /api/synthesis/tasks   # body= {task_type, query, evidence_refs}
```

推荐 smoke 包（已在 golden 中，类型齐全）：

| smoke | task_type | 参考 golden 包 |
|---|---|---|
| 1 | summary | task_001（HBM4 位宽演进） |
| 2 | comparison | task_009（单相 vs 两相浸没式） |
| 3 | causal_synthesis | task_018（AI 算力→液冷因果） |
| 4 | tension_extraction | task_025（封装价值提升 vs 供应链瓶颈张力） |

## 2. 在外部工具中执行（Task 8 验证完整链路）

对每个任务：

1. Task Center 打开任务目录（「打开目录」）→ 复制「启动提示词」。
2. 在 Trae / Codex / Qwen Code / Claude Code 打开任务目录，把 AGENT_INSTRUCTION_V1.md 作为指令粘贴。
3. 让工具读取 `evidence.jsonl`，调用你选定的模型，生成 `result/result.json` + `run_meta.json`。
4. 把任务目录移到 `D:\AI知识整合体系\taskpacks\completed\<task_id>\`，或确认完成后手动移动，并确保 `result/DONE` 存在。

预期状态流转：Create（READY）→ 外部 Agent → DONE → Watcher → Validator → Viewer（COMPLETED / IMPORTED）。

## 3. 校验（无模型）

```bash
# importer 八步 Gate / API rescan：在 Task Center 刷新，或
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

执行 `taskpack_eval.py --runs runs/<worker>` 核对硬 Gate（§74），并按 Entailment 审核表人工标注（≥90%）与终审 Critical Contradiction = 0。

## 6. 完成后

对照 IMPLEMENTATION_STATUS.md 的 L1 TaskPack 章节，把 Task 9/10 结果与评估写入 `L1A_TASKPACK_EVALUATION.md` 后即可收尾。V3.0 §76：**不进入 L1B**（不自动开发 LLM 自主检索 / Agent 自动研究 / Draft→Proposal / MCP）。