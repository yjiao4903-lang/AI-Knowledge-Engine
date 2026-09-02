# AI-Knowledge-Engine Current State

更新日期：2026-09-02  
阶段：I8 Research OS Integration — Phase 2

## 当前定位

```text
AI-Knowledge-Engine
= Evidence / Retrieval / TaskPack / Validation Engine
+ Research Workflow Host
```

Cognition App 仍是唯一正式认知写入者。

## 已完成

### Retrieval / Evidence
- Report Parser / Chunker / SQLite / FTS / Dense / Hybrid / Reranker；
- 全量报告索引与 Golden Regression；
- Cognition Markdown 只读派生索引，独立 catalog / Qdrant collection；
- Qdrant degraded 边界；
- 默认工作台改为 `lexical + rerank OFF`，语义/混合显式启用；
- Search Result 可加入 Evidence Basket；
- Basket 以 localStorage 持久化、按 `chunk_id` 去重；
- TaskPack Builder 仍从 catalog 权威解析 Evidence 正文。

### TaskPack / External AI
- TaskPack V1 Builder / External Worker / Importer Gate；
- 结构化 `CognitionContextItem V1`；
- `Search -> Evidence Basket -> Create TaskPack` 已闭环；
- Task Center 可查看结构化 Result；
- INVALID_RESULT 可读但不可发布 Proposal。

### Cognition Integration
- TaskPack -> Cognition Proposal Candidate 保守转换；
- `supported` 不会升级为 `verified_fact`；
- 新增 Cognition HTTP Gateway；
- KE 只允许调用 Cognition `POST /api/proposals` 创建 staging candidate；
- 新增 Proposal 发布幂等 marker：`result/proposal_publish.json`；
- KE 不暴露 Apply / Merge / Revision / Topic Update 能力；
- Task Center 可将通过 Gate 的结果发送到 Cognition Proposal 区；
- 正式变化继续由 Cognition Preview + Human Apply 完成。

### Runtime / Lifecycle
- Unified runtime / health / backup / restore 已迁入主仓；
- TaskPack 默认根 `<repo>/data/taskpacks`；
- 旧 TaskPack 安全迁移脚本；
- Cognition Markdown + durable TaskPack backup；
- Report watcher 与 Cognition watcher 已拆分职责，避免重复 cognition reconcile。

### CI
GitHub Actions：`.github/workflows/i8-ci.yml`

覆盖：
- Backend I8 Phase 1 + Phase 2 contracts；
- 前端 TypeScript/Vite build；
- Runtime PowerShell syntax。

Phase 1 CI 已 PASS；Phase 2 当前分支持续由同一 workflow 检查。

## 永久边界

```text
Cognition App = only formal cognition writer
KE = Evidence/TaskPack host + Proposal staging client
External Worker = synthesis executor
```

禁止：
- KE 直接写 Cognition Markdown；
- KE 调用 Proposal Apply；
- KE 调用 merge / revision / topic update 正式写接口；
- Report/Cognition SQLite 合并；
- Report/Cognition Qdrant collection 混用；
- TaskPack `supported` 自动映射 `verified_fact`；
- AI output 自动晋升正式知识。

## 当前关键 API

```text
POST /api/search
POST /api/synthesis/tasks
GET  /api/synthesis/tasks
GET  /api/synthesis/tasks/{task_id}
GET  /api/synthesis/tasks/{task_id}/proposal-candidates
POST /api/synthesis/tasks/{task_id}/rescan

GET  /api/research-os/cognition/health
GET  /api/research-os/tasks/{task_id}/proposal-publication
POST /api/research-os/tasks/{task_id}/publish-proposal

GET  /api/taskpack/runs
GET  /api/health
```

## 当前用户路径

```text
关键词/语义/混合搜索
→ 选择 Evidence
→ Evidence Basket
→ 创建 TaskPack
→ External Worker
→ Importer Gate
→ Result Viewer
→ 发送到 Cognition Proposal
→ Cognition Preview / Apply / Reject / Defer
```

## 运行配置

Cognition API：

```text
http://127.0.0.1:3220/api
```

环境覆盖：

```text
COGNITION_API_URL
COGNITION_DATA_ROOT
AIKE_TASKPACK_ROOT
AIKE_KB_ROOT
AIKE_MODEL_ROOT
AIKE_KE_PORT
```

## 仍需真机验收

GitHub Actions 无法代替本机：

- Windows + RX 7900 XTX / ROCm；
- 真实 Qdrant corpus；
- `E:\CODEX\AI深度研究\cognition-app`；
- 实际 External Worker；
- Cognition Proposal Preview / Apply；
- 旧 TaskPack 数据迁移。

本机建议：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1
# 确认后
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1 -Apply

.venv\Scripts\python.exe -m pytest backend\tests\ -q
cd frontend; npm run build; cd ..
powershell -ExecutionPolicy Bypass -File .\runtime\health.ps1
.venv\Scripts\python.exe backend\scripts\integration_smoke.py
powershell -ExecutionPolicy Bypass -File .\runtime\backup.ps1 -VerifyAfter
```

## 下一批开发优先级

1. Lexical metadata pre-filter：把过滤条件推进 FTS `LIMIT` 前，解决 scoped search 漏召回；
2. Deterministic Epistemic Linter：预测/估算/强因果 overclaim 检查；
3. Evidence Context Expansion：NONE / NEIGHBOR_1 / SECTION，仍保持独立 chunk identity；
4. TaskPack validation cache，减少轮询重复 Gate；
5. Personal Retrieval Feedback，建立真实用户 benchmark。
