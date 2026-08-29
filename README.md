# AI Knowledge Engine

AI 深度报告本地知识检索系统。

## 目录约定

- 知识源（只读）：`D:\AI深度报告归档`
- 项目根：本目录 `D:\AI-Knowledge-Engine`
- 模型根：`D:\AI-Models`
- Python 虚拟环境：`.venv`（Python 3.12）

## 环境摘要

| 组件 | 版本 / 状态 |
|---|---|
| Python | 3.12.10（`.venv`） |
| Git | 2.55.0.windows.3 |
| Docker Desktop | 4.88.1（CLI 29.7.2） |
| SQLite FTS5 | 可用（含 trigram），pytest 4/4 |
| GPU | AMD RX 7900 XTX — torch 2.9.1+rocm7.13.0，smoke PASS |
| Qdrant | Docker v1.19.0，127.0.0.1:6333 |
| 模型 | Qwen3-Embedding-0.6B / Qwen3-Reranker-0.6B（`D:\AI-Models`） |

## 开发阶段

- [x] 环境扫描 / 安装 P0
- [x] Milestone 0：环境与硬件验证（详见 `docs/IMPLEMENTATION_STATUS.md`）
- [ ] Milestone 1：项目骨架与 Storage
- [ ] M2-M9：Parser / Chunker / Lexical / Dense / Hybrid / Reranker / Eval
- [ ] Gate A 通过后：FastAPI + React 前端

## 常用命令

```powershell
# 依赖安装（含 ROCm torch、冒烟测试）
powershell -ExecutionPolicy Bypass -File scripts\install_deps.ps1

# M0 冒烟测试（GPU 崩溃时自动 CPU fallback）
powershell -ExecutionPolicy Bypass -File scripts\run_m0_smoke.ps1

# Qdrant
docker compose up -d

# 测试
.venv\Scripts\python.exe -m pytest backend\tests/
```

## 提交身份

本仓库使用本地 Git 身份（未配置全局）：
`AI-KB-Local <ai-kb-local@localhost>`