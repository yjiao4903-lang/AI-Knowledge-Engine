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
| SQLite FTS5 | 可用（含 trigram） |
| GPU | AMD RX 7900 XTX（ROCm/PyTorch 待配置） |

## 开发阶段

- [x] 环境扫描 / 安装 P0
- [ ] Milestone 0：Parser / Chunker / SQLite / API / Evaluation
- [ ] Dense / Reranker（需 ROCm）
- [ ] React 前端

## 提交身份

本仓库使用本地 Git 身份（未配置全局）：
`AI-KB-Local <ai-kb-local@localhost>`