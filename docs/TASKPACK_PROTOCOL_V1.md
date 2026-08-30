# TaskPack Protocol V1

> 版本：1.0 ｜ 日期：2026-08-30 ｜ 依据：Personal AI Research OS：L1 TaskPack 外部模型工作流开发实施方案 V3.0（§5-§29/§66）
> 维护方：L1 开发窗口（KE 侧 `backend/app/taskpack/`）
> 定位：Research OS 与任何外部文本模型 / Agent 之间**唯一正式交互协议**（V3.0 §4）。

---

## 1. 目的

Research OS 不再运行任何内部文本大模型（V3.0 §0）。模型能力外置，认知治理内置：
系统只 **生成标准 TaskPack → 固化 Prompt/Evidence/Schema → 等待外部 Worker 写回结果 →
校验 Grounding/Citation/Manifest → 展示 SynthesisDraft**（§0）。

本协议定义 TaskPack 的目录契约、文件格式、状态机、八步 Gate，以及后续评估（§54-§57）。

## 2. 系统边界

```text
Cognition App / KE 前端      →  Create TaskPack（UI），读 Task Center，看 Draft
      ▼
AI Knowledge Engine (KE)     →  EvidenceResolver / Builder / Importer / Validator
      ▼
D:\AI知识整合体系\taskpacks   →  目录契约（任务包落盘点）
      ▼
External Worker              →  Trae / Codex / Qwen Code / Claude Code / 其他
                                读取任务包 → 调用其模型 → 写 result.json
```

## 3. TaskPack 根目录（§5）

固定建议：`D:\AI知识整合体系\taskpacks`（可配置，见 `cfg.taskpack.root_dir`）。

```text
taskpacks/
├─ templates/               正典模板（AGENT_INSTRUCTION_V1.md / OUTPUT_SCHEMA_V1.json / TASKPACK_README.md）
├─ outbox/                  新建任务包（READY）
├─ processing/              处理中
├─ completed/               已写回结果（COMPLETED / INVALID_RESULT / IMPORTED）
├─ failed/                  失败（FAILED）
└─ archive/                 已归档（ARCHIVED）
```

## 4. 单任务包内容（§6）

`<root>/outbox/<task_id>/` 或等价目录：

| 文件 | 说明 | 生成方 |
|---|---|---|
| `task.yaml` | 任务身份 / 权限 / 约束 / 期望输出（§7） | Builder |
| `AGENT_INSTRUCTION.md` | 固化工人指令（§6） | Builder（模板） |
| `evidence.jsonl` | Fixed Evidence Set（§9），每行一个 `TaskPackEvidence` | Builder |
| `cognition_context.jsonl` | 可选认知上下文快照（§10） | Builder（仅提供时） |
| `output_schema.json` | 机器输出 Schema（SynthesisDraftV1，§13） | Builder（模板） |
| `README.md` | 任务包说明（§6） | Builder |
| `manifest.json` | 不可变输入 sha256 清单（§11） | Builder（最后写） |
| `result/` | Worker 写回区（`result.json` / `run_meta.json` / `DONE` 等） | Worker |

## 5. 状态机（§40-§41）

事实依据 = **目录位置 + marker 文件**：

| 状态 | 位置 / marker |
|---|---|
| `READY` | `outbox/` |
| `PROCESSING` | `processing/`；或 `completed/` 无 DONE、`failed/` 无 FAILED |
| `COMPLETED` | `completed/` + `result/DONE` |
| `FAILED` | `failed/` + `result/FAILED` |
| `INVALID_RESULT` | `completed/` + `result/INVALID`（八步 Gate 失败） |
| `IMPORTED` | `completed/` + `result/IMPORTED`（已接收至 Viewer） |
| `ARCHIVED` | `archive/` |

## 6. 外部 Worker 职责（§28/§29）

1. 完整读取任务包内文件（不得读包外）。
2. 只依据 `evidence.jsonl` 产出事实性结论；`evidence_refs` **逐字复制 chunk_id**（§16）。
3. 写 `result/result.json`（严格符合 `output_schema.json`，UTF-8，无 code fence，无 CoT）。
4. 写 `result/run_meta.json`（含 `prompt_sha256` = `task.yaml`+`AGENT_INSTRUCTION.md`+`manifest.json` 对应的清单值；见 Importer Gate 4 校验对象）。
5. 写 `result/DONE`（最后写）；失败写 `result/error.json` + `result/FAILED`。

详见 `TASKPACK_WORKER_GUIDE.md`。

## 7. Importer 八步 Gate（§46）

KE `TaskPackImporter` 对每个带 `result/DONE` 的任务按序校验：

1. **manifest**：manifest.json 合法 + `files` 中每个文件 sha256 一致 + evidence/cognition 计数一致
2. **result_schema**：result.json 符合 `SynthesisDraftV1`
3. **task_id**：result.task_id == task.task_id
4. **prompt_sha**：run_meta.prompt_sha256 == 任务包内 `AGENT_INSTRUCTION.md` 的 sha256；run_meta.task_manifest_sha256 == 任务包内 `manifest.json` 的 sha256
5. **evidence_membership**：claims/tensions 引用的 chunk_id ⊆ evidence.jsonl
6. **citation_invalid**：无引用未提供证据（复用 `validate_draft`）
7. **citation_coverage**：事实性 claim 绑定有效证据比例 ≥ 95%（§22, Gate）
8. **unsupported_claim**：事实性 claim 无证据比例 ≤ 5%（§24, Gate）
9. **stale**：evidence content_hash 与 catalog 当前一致（§48；仅标注，不自动改写）

任何失败 → 标记 `INVALID_RESULT`，**不进入 Viewer**。

## 8. API（KE，§34-§39）

| 端点 | 说明 |
|---|---|
| `POST /api/synthesis/tasks` | 创建 TaskPack，立即返回 `READY` |
| `GET  /api/synthesis/tasks` | Task Center 列表（先触发 scan） |
| `GET  /api/synthesis/tasks/{id}` | 单任务详情 |
| `POST /api/synthesis/tasks/{id}/rescan` | 触发导入（前端轮询） |
| `POST /api/synthesis/tasks/{id}/archive` | 移入 archive |
| `POST /api/synthesis/tasks/{id}/open-folder` | 打开任务目录（白名单） |
| `GET  /api/synthesis/tasks/{id}/prompt` | 复制启动提示词 |

废弃：`POST /api/synthesis`（同步合成）、`POST /api/synthesis/run-model`。

## 9. 评估（§54-§57，Task 10）

- 32 条 Golden → `data/taskpack_golden/task_001..032`（固定输入包，`backend/scripts/migrate_golden_taskpacks.py`）。
- 各模型结果放 `data/taskpack_golden/runs/<worker>/`。
- `backend/scripts/taskpack_eval.py` 不调用模型，按八步 Gate 计算
  Schema Validity / Citation Coverage / Unsupported Claim / Invalid Citation 并输出人工 Entailment 审核表。

## 10. Schema 版本化（§66）

TaskPack / result 均显式版本化（`taskpack_version` / `schema_version`）。升级时新增版本号，
不原地变更字段语义（`ConfigDict(extra="allow")` 兼容无害附加元数据）。