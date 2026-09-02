# AI-Knowledge-Engine Current State

更新日期：2026-09-02  
阶段：Research OS 实用化 / P1 研究质量增强

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
- Lexical metadata filter 已推进 FTS `LIMIT` 前，scoped search 不再因全库 Top-K 截断弱排名目标；
- Search Result 可加入 Evidence Basket；
- Basket 以 localStorage 持久化、按 `chunk_id` 去重；
- TaskPack Builder 仍从 catalog 权威解析 Evidence 正文。

### TaskPack / External AI
- TaskPack V1 Builder / External Worker / Importer Gate；
- 结构化 `CognitionContextItem V1`；
- `Search -> Evidence Basket -> Create TaskPack` 已闭环；
- Task Center 可查看结构化 Result；
- INVALID_RESULT 可读但不可发布 Proposal。

### Research Quality / Epistemic Review
- Deterministic Epistemic Linter 已接入 Proposal Candidate；
- `FORECAST_MARKED_SUPPORTED`：预测/估算/目标类 claim 标成 `supported` 时 warning；
- `CAUSAL_STRENGTH_UNDERGROUNDED`：claim 使用强因果，但引用 Evidence 快照没有显式强因果措辞时 warning；
- `TENSION_INSUFFICIENT_EVIDENCE_DIVERSITY`：tension 少于 2 条不同 Evidence 引用时 warning；
- Linter 仅提供 deterministic review warning，不做 semantic entailment；
- Linter 不修改 `ResultEnvelope`、Claim state，不把 warning 升级成 INVALID_RESULT；
- Warning 会进入 Proposal `warnings[]` 与 `[Research OS Review Warnings]` description 区块，供 Human Preview 复核。

### Cognition Integration
- TaskPack -> Cognition Proposal Candidate 保守转换；
- `supported` 不会升级为 `verified_fact`，仍固定映射为 Cognition `inference`；
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
- Backend Research OS contracts；
- Retrieval regression / lexical metadata pre-filter regression；
- Deterministic Epistemic Linter unit + Proposal integration contracts；
- 前端 TypeScript/Vite build；
- Runtime PowerShell syntax。

CI 保持 lightweight：不安装本地 Embedding/Reranker 模型，不要求 Qdrant / ROCm / 真实 Cognition App。

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
- Epistemic Linter 自动改写 Claim state；
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
→ Deterministic Epistemic Warning
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

1. Evidence Context Expansion：NONE / NEIGHBOR_1 / SECTION，仍保持独立 `chunk_id` identity；
2. TaskPack Validation Cache：按 `result_hash + validation_version` 避免轮询重复完整 Gate；
3. Personal Retrieval Feedback：积累真实 `useful / selected_as_evidence` 数据后再调 retrieval；
4. External Worker Launcher：只负责启动外部程序 / 设置 cwd / 传路径，不把外部模型 SDK 塞回 KE。
