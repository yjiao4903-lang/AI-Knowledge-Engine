# Integration Contract V2 — Personal Research OS

版本：2.0  
日期：2026-09-01  
状态：I8 Phase 1

## 1. 系统职责

```text
Cognition App
= Product Shell + Cognition Control Plane + only formal cognition writer

AI Knowledge Engine
= Evidence + Retrieval + TaskPack + Validation + integration candidate producer

External Worker
= Explicit synthesis executor (Codex / Claude Code / Trae / etc.)
```

永久边界：

1. Knowledge Engine 不直接创建/修改 Judgment、Question、Topic、Proposal Markdown；
2. Cognition Markdown 仍是正式认知唯一事实来源；
3. Report catalog、Cognition derived catalog、Qdrant collections 继续物理隔离；
4. 所有正式认知变化必须经 Cognition `Proposal -> Preview -> Human Apply`；
5. TaskPack result 是研究草稿，不是正式认知。

---

## 2. 核心链路

V1：

```text
Report -> Retrieval -> Evidence -> Proposal -> Human -> Cognition
```

V2：

```text
Report / Cognition Search
        ↓
Evidence + Cognition Context
        ↓
TaskPack
        ↓
External Worker
        ↓
ResultEnvelope
        ↓
KE Validation Gate
        ↓
Proposal Candidate Payload
        ↓
Cognition Proposal
        ↓
Preview + Human Apply
        ↓
Formal Cognition
```

---

## 3. EvidenceReference V1

继续沿用 V1，不创建新的 Evidence ID 体系。

持久 Identity：

```text
source_type
document_id
section_id
chunk_id
content_hash
start_line
end_line
```

检索 score/rank 仅是 trace，不得作为持久 Identity。

---

## 4. CognitionContextItem V1

TaskPack 的 Cognition Context 改为结构化共享契约：

```json
{
  "schema_version": "1.0",
  "context_id": "CTX001",
  "object_type": "judgment",
  "object_id": "judgment-uuid",
  "content_hash": "optional-sha256",
  "title": "当前判断",
  "excerpt": "只读快照"
}
```

约束：

- Context 由调用方显式选择；
- KE 只读取/固化快照；
- Context 不授予 KE Cognition 写权限；
- 若存在 hash，应保留用于 stale 检测；
- `SynthesisRequest` 与 `TaskPackV1` 必须使用同一个 Schema。

---

## 5. TaskPack ResultEnvelope

ResultEnvelope 继续使用：

```text
summary
claims[]
tensions[]
uncertainties[]
open_questions[]
additional_evidence_needed[]
worker
generated_at
```

只有通过现有 TaskPack Importer Gate 的 `COMPLETED / IMPORTED` 结果才能转换为 Proposal Candidate。

`INVALID_RESULT` 可以只读查看，但不得生成可提交 Proposal Candidate。

---

## 6. Grounding State 与 Cognition Epistemic State

两个枚举**禁止合并为同一含义**。

### TaskPack grounding_state

```text
supported
inference
hypothesis
uncertain
contradicted
```

含义：在当前 Fixed Evidence Set 下，Worker 输出与证据之间的 grounding 状态。

### Cognition epistemic_state

```text
verified_fact
inference
hypothesis
open_question
counterexample
unknown
```

含义：Personal Research OS 对正式认知对象的认识论分类。

### I8 保守映射

```text
supported    -> inference
inference    -> inference
hypothesis   -> hypothesis
uncertain    -> unknown
contradicted -> counterexample
```

特别禁止：

```text
supported -> verified_fact
```

因为“被本次固定证据支持”不等于“已通过人工审查成为正式已验证事实”。

---

## 7. Proposal Candidate Bridge

新增只读端点：

```text
GET /api/synthesis/tasks/{task_id}/proposal-candidates
```

前置条件：

```text
Task status = COMPLETED | IMPORTED
```

返回：

```json
{
  "task_id": "...",
  "source_status": "COMPLETED",
  "auto_apply": false,
  "target_contract": "Cognition Proposal API V0.2 / POST /api/proposals",
  "proposal_payload": {
    "title": "...",
    "origin_type": "external_llm",
    "origin_ref": "task_id",
    "origin_title": "query",
    "generator": "worker:model",
    "description": "summary",
    "topics": [],
    "items": []
  },
  "warnings": []
}
```

映射：

| TaskPack | Proposal Candidate |
|---|---|
| claim | `new_judgment` candidate |
| tension | `new_tension` |
| open_question | `new_question` |
| additional_evidence_needed | `new_question` |
| uncertainty | warning / review context |

该端点**不调用 Cognition API**。

正式写入仍应由 Cognition App：

```text
GET proposal-candidates
→ 用户检查
→ POST /api/proposals
→ Preview
→ Apply / Reject / Defer
```

---

## 8. 产品入口

正式用户入口仍建议由 Cognition App 承担。

KE React 前端定位：

```text
Retrieval Console
TaskPack Debug
Index / Health
Evaluation
Advanced Search
```

避免在两个前端分别实现：

- Proposal Center；
- Judgment 编辑；
- Topic 更新；
- Human Apply Gate。

---

## 9. Runtime

统一 Runtime 代码迁入本仓：

```text
runtime/research-os.ps1
```

路径通过环境变量覆盖，不再要求 Integration Workspace 本身存在。

启动目标：

```text
Cognition product shell first
→ Qdrant / KE warming
```

KE/Qdrant degraded 不应阻断 Cognition 基础工作台。

---

## 10. Backup Lifecycle

### Tier 1A

正式 Cognition Markdown。

### Tier 1B

不可保证确定性重建的 TaskPack 研究产物：

```text
completed/
archive/
failed/ (audit)
```

未完成：

```text
outbox/
processing/
```

默认不作为长期备份重点。

SQLite / FTS / Qdrant 为派生可重建资产。

---

## 11. 当前禁止事项

- KE 自动 POST Cognition Proposal；
- KE 直接写 Cognition Markdown；
- 两 SQLite 合并；
- 两 Qdrant collection 混为一个语义空间；
- `supported` 自动升级 `verified_fact`；
- External Worker 自动 Apply Proposal；
- TaskPack archive 结果被当成正式知识事实。

---

## 12. I8 Phase 1 Definition of Done

- [x] CognitionContextItem 共享 Schema；
- [x] SynthesisRequest 使用结构化 Cognition Context；
- [x] TaskPack 使用同一 Context Contract；
- [x] TaskPack -> Proposal Candidate pure transformer；
- [x] Proposal Candidate read-only API；
- [x] `auto_apply=false` 写入契约；
- [x] Grounding/Cognition epistemic 保守映射；
- [x] Unified Runtime 迁入 KE 主仓；
- [x] TaskPack durable artifacts 纳入备份政策；
- [x] Cross-system read-only smoke test 脚本。

I8 Phase 2 需在真实 Cognition App 代码仓执行：

```text
Evidence Basket -> Create TaskPack
Task status / Result Viewer
Proposal Candidate -> existing Proposal Center
```
