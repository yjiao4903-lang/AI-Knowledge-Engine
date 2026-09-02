# Research OS Runtime（I8）

本目录将原独立 `AI-knowledge-combine` 工作区中长期有价值的启动、健康检查、备份/恢复职责吸收到 `AI-Knowledge-Engine` 主仓。

它不会合并 Cognition 数据库。I8 Phase 2 中，Knowledge Engine 可以通过 Cognition **官方 Proposal API** 创建 staging candidate，但正式认知变化仍只能由 Cognition `Preview + Human Apply` 完成。

## 推荐入口

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\start.ps1
powershell -ExecutionPolicy Bypass -File .\runtime\health.ps1
powershell -ExecutionPolicy Bypass -File .\runtime\stop.ps1
powershell -ExecutionPolicy Bypass -File .\runtime\backup.ps1 -VerifyAfter
```

底层统一实现为 `research-os.ps1`；wrapper 只是稳定入口。

## TaskPack 旧数据迁移

新默认根：

```text
<AI-Knowledge-Engine>\data\taskpacks
```

旧路径：

```text
D:\AI知识整合体系\taskpacks
```

先 dry-run：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1
```

确认后：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1 -Apply
```

迁移器只复制不删除；同路径同 SHA256 跳过；不同 SHA256 拒绝覆盖；Apply 后重新校验。

## 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `COGNITION_APP_ROOT` | `E:\CODEX\AI深度研究\cognition-app` | Cognition 程序目录 |
| `COGNITION_DATA_ROOT` | `E:\CODEX\AI深度研究\cognition` | 正式 Cognition Markdown |
| `COGNITION_API_URL` | `http://127.0.0.1:3220/api` | KE → Cognition Proposal staging API |
| `AIKE_TASKPACK_ROOT` | `<repo>\data\taskpacks` | TaskPack 根 |
| `AIKE_BACKUP_ROOT` | `<repo>\backups` | 统一备份目录 |
| `AIKE_KE_PORT` | `8765` | Knowledge Engine API |
| `AIKE_COGNITION_PORT` | `3220` | Cognition UI/API 运行端口 |
| `AIKE_QDRANT_CONTAINER` | `ai-kb-qdrant` | Qdrant Docker 容器名 |
| `AIKE_KB_ROOT` | config 默认值 | 报告知识库根 |
| `AIKE_MODEL_ROOT` | config 默认值 | 本地 Embedding/Reranker 模型根 |

如果修改 `AIKE_COGNITION_PORT`，应同步设置对应的 `COGNITION_API_URL`，例如：

```powershell
$env:AIKE_COGNITION_PORT = '3330'
$env:COGNITION_API_URL = 'http://127.0.0.1:3330/api'
```

## 启动语义

```text
Cognition UI
  ↓ 先可用
基础工作台 / legacy fallback

同时准备：
Docker → Qdrant → KE → semantic retrieval
```

KE/Qdrant warming 或降级不应阻断 Cognition 基础使用。

## Cognition 写入边界

允许：

```text
KE -> POST /api/proposals
```

用途仅为创建 Proposal staging candidate。

禁止 KE 调用：

```text
Proposal apply
merge
judgment revision
topic update
archive target
```

因此完整正式链仍是：

```text
TaskPack Result
→ Proposal Candidate
→ Cognition Proposal
→ Preview
→ Human Apply / Reject / Defer
```

## 备份语义

### Tier 1A：Formal Cognition

备份 Cognition Markdown；排除可重建 SQLite/WAL 和历史嵌套 backup。

### Tier 1B：Durable TaskPack Research Artifacts

备份：

- `completed/`
- `archive/`
- `failed/`
- `data/taskpack_golden/runs/`（存在时）

`result/proposal_publish.json` 随 TaskPack 一并备份。

默认不长期备份：`outbox/`、`processing/`。

SQLite / FTS / Qdrant 属于可重建派生资产。

## 恢复

默认先做 manifest-only 验证：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\restore.ps1 -Backup <时间戳或完整路径>
```

推荐恢复到隔离目录演练后，再考虑正式恢复。

## 永久边界

```text
Cognition App = 唯一正式认知写入者
AI Knowledge Engine = Evidence / Retrieval / TaskPack / Proposal-staging client
runtime = orchestration only
```
