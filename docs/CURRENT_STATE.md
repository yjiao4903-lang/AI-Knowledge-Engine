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
- I8 Unified Research OS runtime / health / backup / restore 迁入本仓；
- I8 TaskPack 默认根迁入 `<repo>/data/taskpacks`；
- I8 旧 `D:\AI知识整合体系\taskpacks` 安全迁移脚本；
- I8 Cognition + durable TaskPack backup lifecycle；
- I8 read-only cross-system smoke script；
- I8 KE Task Center 降级为运行/调试控制台，移除固定空 Evidence 的坏创建入口；
- I8 Task Center 可只读查看/复制 Cognition Proposal Candidate JSON。

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

### Runtime / Migration

```text
runtime/research-os.ps1
runtime/start.ps1
runtime/stop.ps1
runtime/health.ps1
runtime/backup.ps1
runtime/restore.ps1
runtime/migrate-taskpacks.ps1
```

### Smoke

`backend/scripts/integration_smoke.py`

### Contract

`docs/INTEGRATION_CONTRACT_V2.md`

## TaskPack 数据迁移

新默认根：

```text
D:\AI-Knowledge-Engine\data\taskpacks
```

旧路径如果仍有历史任务，先 dry-run：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1
```

再显式：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1 -Apply
```

迁移器只复制、不删除旧源，并按 SHA256 检测冲突/复验。

## 下一阶段（需要真实 cognition-app 代码）

`AI-knowledge-combine` GitHub 仓库本身不包含真实 Cognition Vue/Node 源码，因此 I8 Phase 2 不能仅靠该仓继续改 UI。真实代码位于现有本机 Cognition App 目录。

I8 Phase 2：

1. 在 Cognition Evidence Basket 中增加“创建 TaskPack”；
2. 把当前 Judgment / Question / Topic 作为结构化 Cognition Context 传入；
3. Cognition UI 展示 Task 状态与 Result Viewer；
4. 调用 KE `proposal-candidates`；
5. 将返回 payload 交给既有 Cognition Proposal Center；
6. 继续使用 Preview / Apply / Reject / Defer，不新增第二套审批系统。

## 验证状态

本分支已加入 deterministic unit tests 与 cross-system smoke test 脚本；但 GitHub 仓库当前没有 Actions workflow，而且 GitHub Connector 不能替代用户 Windows 主机上的 ROCm、Qdrant、Cognition 实体运行环境。因此本次远程代码整合**不宣称真机测试已经通过**。

合入后在真实 Windows 环境应执行：

```powershell
# 旧 TaskPack 首次迁移（如旧目录存在）
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1 -Apply

# 后端回归
.venv\Scripts\python.exe -m pytest backend\tests\ -q

# 前端类型 + 构建
cd frontend
npm run build
cd ..

# 全栈健康
powershell -ExecutionPolicy Bypass -File .\runtime\health.ps1

# 跨系统只读 smoke
.venv\Scripts\python.exe backend\scripts\integration_smoke.py

# 备份恢复演练建议先用隔离目录
powershell -ExecutionPolicy Bypass -File .\runtime\backup.ps1 -VerifyAfter
```
