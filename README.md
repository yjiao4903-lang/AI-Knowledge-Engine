# AI Knowledge Engine

本地个人研究系统的 **Evidence / Retrieval / TaskPack Engine**。

当前仓库已经吸收原 `AI-knowledge-combine` 中长期需要维护的 Integration Contract、统一 Runtime、Health、Backup 与跨系统 Smoke 能力；正式 Cognition Markdown 仍由独立 Cognition App 负责写入，数据库不合并。

## 系统定位

```text
Cognition App
= 正式产品壳 + Cognition Control Plane + 唯一正式认知写入者

AI Knowledge Engine
= Report/Cognition Retrieval + Evidence + TaskPack + Validation + Proposal Candidate

External Worker
= Codex / Claude Code / Trae 等显式研究综合执行器
```

核心链：

```text
Search
→ Evidence
→ TaskPack
→ External Worker
→ Validated Result
→ Proposal Candidate
→ Cognition Preview / Human Apply
→ Formal Cognition
```

## 目录约定

- 知识源（只读）：`D:\AI深度报告归档`
- 项目根：本仓库
- 模型根：默认 `D:\AI-Models`
- Python 虚拟环境：`.venv`（Python 3.12）
- Cognition 程序：默认 `E:\CODEX\AI深度研究\cognition-app`（可用环境变量覆盖）
- Cognition 数据：默认 `E:\CODEX\AI深度研究\cognition`（正式事实源，KE 只读）

## 环境摘要

| 组件 | 版本 / 状态 |
|---|---|
| Python | 3.12.x（`.venv`） |
| Docker Desktop | 本地 Qdrant runtime |
| SQLite FTS5 | terms + trigram |
| GPU | AMD RX 7900 XTX / ROCm（可 CPU fallback） |
| Qdrant | `127.0.0.1:6333` |
| 模型 | Qwen3-Embedding-0.6B / Qwen3-Reranker-0.6B |

## 已完成阶段

- [x] M0–M11：Parser / Chunker / Lexical / Dense / Hybrid / Reranker / Eval / FastAPI / React
- [x] Integration I0–I7：全量报告、Cognition Retrieval Proxy、Evidence→Proposal、Unified Runtime、Backup、Cognition Search、Stabilization
- [x] TaskPack V3：内部文本 LLM 移除；Builder / External Worker / Importer Gate / runs
- [x] Qdrant degraded 边界：向量不可用时归档/lexical 边界明确
- [x] I8 Phase 1：结构化 Cognition Context + TaskPack→Proposal Candidate + Runtime/Backup 吸收
- [ ] I8 Phase 2：在真实 Cognition App UI 中接入 TaskPack 创建、Result Viewer、Proposal Candidate

当前事实源：`docs/CURRENT_STATE.md`  
新整合契约：`docs/INTEGRATION_CONTRACT_V2.md`

## 常用命令

```powershell
# 依赖安装
powershell -ExecutionPolicy Bypass -File scripts\install_deps.ps1

# 测试
.venv\Scripts\python.exe -m pytest backend\tests\ -q

# Unified Research OS 启动
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action start

# 健康检查
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action health

# Cognition + durable TaskPack 备份
powershell -ExecutionPolicy Bypass -File .\runtime\research-os.ps1 -Action backup -VerifyBackup

# 跨系统只读 smoke（两服务启动后）
.venv\Scripts\python.exe backend\scripts\integration_smoke.py
```

## I8 新端点

通过 TaskPack Gate 的任务可以导出 Cognition Proposal 候选：

```text
GET /api/synthesis/tasks/{task_id}/proposal-candidates
```

该端点只返回候选 payload：

```text
auto_apply = false
```

Knowledge Engine **不会**自动调用 Cognition 写接口。

## 永久边界

禁止：

- KE 创建/修改正式 Judgment / Question / Topic Markdown；
- KE 自动 Apply Proposal；
- Report 与 Cognition SQLite 合库；
- Report 与 Cognition Qdrant collection 混成一个分数空间；
- TaskPack `supported` 自动提升为 Cognition `verified_fact`。

TaskPack 协议与外部 Worker：`docs/TASKPACK_PROTOCOL_V1.md`、`docs/TASKPACK_WORKER_GUIDE.md`。
