# Integration Contract V2 — Personal Research OS

版本：2.1  
日期：2026-09-02  
状态：I8 Phase 2

## 1. 系统职责

```text
Cognition App
= Cognition Control Plane + only formal cognition writer

AI Knowledge Engine
= Evidence + Retrieval + TaskPack + Validation + Research Workflow Host

External Worker
= Explicit synthesis executor
```

永久边界：

1. KE 不直接创建/修改 Judgment、Question、Topic Markdown；
2. Cognition Markdown 仍是正式认知唯一事实来源；
3. Report catalog、Cognition derived catalog、Qdrant collections 继续物理隔离；
4. KE **允许通过 Cognition 官方 HTTP API 创建 Proposal staging candidate**；
5. KE **不得调用** Proposal apply、merge、judgment revision、topic update 等正式认知写动作；
6. 所有正式认知变化仍必须经 Cognition `Proposal -> Preview -> Human Apply`；
7. TaskPack result 是研究草稿，不是正式认知。

---

## 2. 核心链路

```text
Report / Cognition Search
        ↓
Evidence Basket + Cognition Context
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
KE Cognition Gateway
        ↓ POST /api/proposals only
Cognition Proposal Staging
        ↓
Preview + Human Apply / Reject / Defer
        ↓
Formal Cognition
```

---

## 3. EvidenceReference V1

继续沿用原 Identity：

```text
source_type
document_id
section_id
chunk_id
content_hash
start_line
end_line
```

score/rank 仅用于 retrieval trace，不得作为持久 Identity。

Evidence Basket 可以缓存 excerpt 用于 UI，但 TaskPack Builder 必须按 `chunk_id` 从权威 catalog 重新解析正文。

---

## 4. CognitionContextItem V1

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

约束：Context 由用户显式选择；KE 只读取/固化快照；Context 不授予正式认知写权限。

---

## 5. TaskPack ResultEnvelope

核心字段：

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

只有通过 Importer Gate 的 `COMPLETED / IMPORTED` 任务允许发布 Proposal。

`INVALID_RESULT` 可只读查看，但禁止发布 Proposal。

---

## 6. Grounding 与 Cognition Epistemic State

TaskPack：

```text
supported / inference / hypothesis / uncertain / contradicted
```

Cognition：

```text
verified_fact / inference / hypothesis / open_question / counterexample / unknown
```

保守映射：

```text
supported    -> inference
inference    -> inference
hypothesis   -> hypothesis
uncertain    -> unknown
contradicted -> counterexample
```

明确禁止：`supported -> verified_fact`。

---

## 7. Proposal Candidate API

只读转换：

```text
GET /api/synthesis/tasks/{task_id}/proposal-candidates
```

映射：

| TaskPack | Cognition Candidate |
|---|---|
| claim | `new_judgment` |
| tension | `new_tension` |
| open_question | `new_question` |
| additional_evidence_needed | `new_question` |
| uncertainty | warning / review context |

---

## 8. Cognition Gateway

I8 Phase 2 允许 KE 使用 Cognition 官方 Proposal staging API：

```text
POST /api/proposals
GET  /api/proposals/{id}
GET  /api/settings        # health probe
```

KE 端公开：

```text
GET  /api/research-os/cognition/health
GET  /api/research-os/tasks/{task_id}/proposal-publication
POST /api/research-os/tasks/{task_id}/publish-proposal
```

发布行为：

1. Task 必须 `COMPLETED / IMPORTED`；
2. 生成 Proposal Candidate；
3. 仅调用 Cognition `POST /api/proposals`；
4. 本地写 `result/proposal_publish.json` 作为幂等/追踪 marker；
5. 重复发布默认复用 marker；
6. `auto_apply=false` 永久写入契约。

Gateway 代码**不得提供**：

```text
apply_proposal
merge
revise_judgment
update_topic
archive_target
```

正式 Cognition 变化仍只能在 Cognition UI 中逐项 Preview / Apply / Reject / Defer。

---

## 9. 产品工作流

I8 Phase 2 的主仓用户路径：

```text
Search
→ Add Evidence
→ Evidence Basket
→ Create TaskPack
→ External Worker
→ Result Viewer
→ Publish Proposal Candidate
→ Cognition Proposal Center
→ Human Review
```

默认 Search 工作台为 `lexical + rerank OFF`；语义/混合为显式选择。

KE 不实现第二套 Judgment/Topic 编辑器或 Proposal Apply Center。

---

## 10. Runtime / Config

Cognition Proposal API 默认：

```text
http://127.0.0.1:3220/api
```

可用：

```text
COGNITION_API_URL
```

覆盖。

TaskPack 根默认：

```text
<repo>/data/taskpacks
```

---

## 11. Backup Lifecycle

Tier 1A：正式 Cognition Markdown。  
Tier 1B：TaskPack `completed/ archive/ failed/` 研究产物。

SQLite / FTS / Qdrant 是派生可重建资产。

`proposal_publish.json` 位于 TaskPack result 内，因此随 durable TaskPack 一并备份。

---

## 12. 当前禁止事项

- KE 直接写 Cognition Markdown；
- KE 调用 Cognition Proposal Apply；
- KE 调用 merge/revision/topic update 正式写接口；
- 两 SQLite 合并；
- 两 Qdrant collection 合并；
- `supported` 自动升级 `verified_fact`；
- External Worker 自动 Apply Proposal；
- TaskPack 结果自动晋升正式知识。

---

## 13. I8 Phase 2 Definition of Done

- [x] Search Result → Evidence Basket；
- [x] Basket 持久化与去重；
- [x] Basket → real TaskPack；
- [x] 默认 lexical / rerank OFF；
- [x] Task Result Viewer；
- [x] Cognition Proposal HTTP Gateway；
- [x] Proposal publication marker / idempotency；
- [x] Gateway 无 Apply/Merge/Revision surface；
- [x] Report/Cognition watcher 职责分离；
- [x] CI 覆盖 Phase 2 contract + frontend build + PowerShell syntax。

仍需真实 Windows 环境做端到端运行验收：Cognition API、Qdrant/ROCm、External Worker、Proposal Center Preview/Apply。
