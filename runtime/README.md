# Research OS Runtime（I8）

`runtime/research-os.ps1` 将原独立 `AI-knowledge-combine` 工作区中长期有价值的启动、健康检查与备份职责吸收到 `AI-Knowledge-Engine` 主仓。

它**不会**合并 Cognition 数据库，也不会赋予 Knowledge Engine 正式认知写权限。

## 用法

```powershell
# 启动：先拉起 Cognition 产品壳，再准备 Qdrant / KE
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action start

# 不自动打开浏览器
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action start -NoBrowser

# 健康检查
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action health

# 停止本脚本记录的进程；默认保留 Qdrant
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action stop

# 连 Qdrant 一起停
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action stop -StopQdrant

# 备份正式 Cognition + durable TaskPack 研究产物
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action backup -VerifyBackup
```

## 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `COGNITION_APP_ROOT` | `E:\CODEX\AI深度研究\cognition-app` | Cognition 程序目录 |
| `COGNITION_DATA_ROOT` | `E:\CODEX\AI深度研究\cognition` | 正式 Cognition Markdown |
| `AIKE_TASKPACK_ROOT` | `D:\AI知识整合体系\taskpacks` | 当前 TaskPack 根；迁移后可改为主仓目录 |
| `AIKE_BACKUP_ROOT` | `<repo>\backups` | 统一备份目录 |
| `AIKE_KE_PORT` | `8765` | Knowledge Engine API |
| `AIKE_COGNITION_PORT` | `3220` | Cognition UI/API |
| `AIKE_QDRANT_CONTAINER` | `ai-kb-qdrant` | Qdrant Docker 容器名 |

## 启动语义

产品壳优先：

```text
Cognition UI
  ↓ 先可用
基础工作台 / legacy fallback

同时准备：
Docker → Qdrant → KE → semantic retrieval
```

因此 KE/Qdrant warming 或降级不应阻断 Cognition 的基础使用。

## 备份语义

### Tier 1A：Formal Cognition

备份 Cognition Markdown，全量保留；排除可重建的：

- `index.qlite`
- `index.qlite-wal`
- `index.qlite-shm`
- Cognition 自己的历史 `backups` 目录

### Tier 1B：Durable TaskPack Research Artifacts

备份：

- `completed/`
- `archive/`
- `failed/`（用于审计和恢复）
- `data/taskpack_golden/runs/`（存在时）

默认不备份：

- `outbox/`
- `processing/`

因为这些属于未完成执行状态。

SQLite / FTS / Qdrant 仍属于可重建派生资产，不作为唯一备份。

## 永久边界

```text
Cognition App = 唯一正式认知写入者
AI Knowledge Engine = Evidence / Retrieval / TaskPack Engine
runtime = orchestration only
```

TaskPack 结果只能生成 Proposal Candidate；正式变更仍需 Cognition `Preview + Apply`。
