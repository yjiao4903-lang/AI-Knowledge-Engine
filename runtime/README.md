# Research OS Runtime（I8）

本目录将原独立 `AI-knowledge-combine` 工作区中长期有价值的启动、健康检查、备份/恢复职责吸收到 `AI-Knowledge-Engine` 主仓。

它**不会**合并 Cognition 数据库，也不会赋予 Knowledge Engine 正式认知写权限。

## 推荐入口

```powershell
# 启动
powershell -ExecutionPolicy Bypass -File .\runtime\start.ps1

# 启动但不由本 wrapper 主动打开浏览器
powershell -ExecutionPolicy Bypass -File .\runtime\start.ps1 -NoBrowser

# 健康检查
powershell -ExecutionPolicy Bypass -File .\runtime\health.ps1

# 停止；默认保留 Qdrant
powershell -ExecutionPolicy Bypass -File .\runtime\stop.ps1

# 连 Qdrant 一起停
powershell -ExecutionPolicy Bypass -File .\runtime\stop.ps1 -Qdrant

# 备份并回读校验
powershell -ExecutionPolicy Bypass -File .\runtime\backup.ps1 -VerifyAfter
```

底层统一实现为 `research-os.ps1`；兼容 wrapper 只是稳定入口，不复制逻辑。

## TaskPack 从旧 Integration Workspace 迁移

I8 后默认 TaskPack 根为：

```text
<AI-Knowledge-Engine>\data\taskpacks
```

旧路径：

```text
D:\AI知识整合体系\taskpacks
```

如果旧路径存在，先 dry-run：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1
```

确认后：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1 -Apply
```

迁移器：

- 只复制，不删除旧源；
- 同路径同 SHA256 自动跳过；
- 同路径不同 SHA256 直接失败，不覆盖；
- Apply 后逐文件 SHA256 复验。

因此可以先完成代码切换，再在本机显式执行一次数据迁移。

## 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `COGNITION_APP_ROOT` | `E:\CODEX\AI深度研究\cognition-app` | Cognition 程序目录 |
| `COGNITION_DATA_ROOT` | `E:\CODEX\AI深度研究\cognition` | 正式 Cognition Markdown |
| `AIKE_TASKPACK_ROOT` | `<repo>\data\taskpacks` | TaskPack 根 |
| `AIKE_BACKUP_ROOT` | `<repo>\backups` | 统一备份目录 |
| `AIKE_KE_PORT` | `8765` | Knowledge Engine API |
| `AIKE_COGNITION_PORT` | `3220` | Cognition UI/API |
| `AIKE_QDRANT_CONTAINER` | `ai-kb-qdrant` | Qdrant Docker 容器名 |
| `AIKE_KB_ROOT` | config 默认值 | 报告知识库根 |
| `AIKE_MODEL_ROOT` | config 默认值 | 本地 Embedding/Reranker 模型根 |

这些与后端 `load_config()` 的 I8 override 对齐，避免 runtime 与 KE 读取不同目录。

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

注意：如果 Cognition 自身 `start.bat` 内部仍主动打开浏览器，则 `-NoBrowser` 只能保证本 runtime wrapper 不额外打开一次；不会改写 Cognition 自身启动脚本。

## 备份语义

### Tier 1A：Formal Cognition

备份 Cognition Markdown，全量保留；排除可重建的：

- `index.qlite`
- `index.qlite-wal`
- `index.qlite-shm`
- `90_系统\backups` 历史嵌套目录

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

## 恢复

先做 manifest-only 校验：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\restore.ps1 -Backup <时间戳或完整路径>
```

默认**不会覆盖任何数据**。

在隔离目录演练恢复：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\restore.ps1 `
  -Backup <时间戳> `
  -RestoreCognitionDir D:\RestoreDrill\cognition `
  -RestoreTaskpackDir D:\RestoreDrill\taskpacks `
  -Force
```

推荐先在隔离目录验证，再考虑恢复正式目录。恢复后应重建派生索引。

## 永久边界

```text
Cognition App = 唯一正式认知写入者
AI Knowledge Engine = Evidence / Retrieval / TaskPack Engine
runtime = orchestration only
```

TaskPack 结果只能生成 Proposal Candidate；正式变更仍需 Cognition `Preview + Apply`。
