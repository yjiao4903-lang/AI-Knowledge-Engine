# AI-Knowledge-Engine Current State

更新日期：2026-09-01  
阶段：I8 Research OS Integration — Phase 1

## 当前定位

```text
AI-Knowledge-Engine
= Evidence / Retrieval / TaskPack / Validation Engine
+ Research OS integration host
```

正式 Cognition 写权限仍不在本仓。

## 已完成能力

- Report Parser / Chunker / SQLite / FTS / Dense / Hybrid / Reranker；
- 全量终版报告索引与 Golden Regression；
- Cognition Markdown 只读派生索引与独立 Qdrant collection；
- Qdrant degraded 明确边界；
- TaskPack V1 Builder / External Worker / Importer Gate / runs 读取；
- I8 共享 `CognitionContextItem V1`；
- I8 TaskPack -> Cognition Proposal Candidate 只读转换；
- I8 Unified Research OS runtime 迁入本仓；
- I8 Cognition + durable TaskPack backup lifecycle；
- I8 read-only cross-system smoke script。

## 永久边界

```text
Cognition App = only formal cognition writer
KE = read-only consumer of Cognition + candidate producer
External Worker = synthesis executor
```

禁止：

- KE 直接写 Cognition Markdown；
- KE 自动 Apply Proposal；
- Report/Cognition SQLite 合并；
- Report/Cognition Qdrant collection 混用；
- TaskPack `supported` 自动映射 `verified_fact`。

## 当前关键 API

```text
POST /api/search
POST /api/synthesis/tasks
GET  /api/synthesis/tasks
GET  /api/synthesis/tasks/{task_id}
GET  /api/synthesis/tasks/{task_id}/proposal-candidates   # I8
POST /api/synthesis/tasks/{task_id}/rescan
GET  /api/taskpack/runs
GET  /api/search/cognition (按当前实现/配置)
GET  /api/health
```

## I8 Phase 1 输出

### Shared Contract

`backend/app/contracts/cognition.py`

### Proposal Bridge

`backend/app/integration/proposals.py`

### Runtime

`runtime/research-os.ps1`

### Smoke

`backend/scripts/integration_smoke.py`

### Contract

`docs/INTEGRATION_CONTRACT_V2.md`

## 下一阶段（需要真实 cognition-app 代码）

I8 Phase 2：

1. 在 Cognition Evidence Basket 中增加“创建 TaskPack”；
2. 把当前 Judgment / Question / Topic 作为结构化 Cognition Context 传入；
3. Cognition UI 展示 Task 状态与 Result Viewer；
4. 调用 KE `proposal-candidates`；
5. 将返回 payload 交给既有 Cognition Proposal Center；
6. 继续使用 Preview / Apply / Reject / Defer，不新增第二套审批系统。

## 验证状态

本分支已加入 deterministic unit tests 与 read-only smoke test脚本；由于 GitHub 仓库当前没有 Actions workflow，本次远程改动本身不等价于本机 runtime 验收。合入后应在真实 Windows 环境执行：

```powershell
.venv\Scripts\python.exe -m pytest backend\tests\ -q
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action health
.venv\Scripts\python.exe backend\scripts\integration_smoke.py
```
