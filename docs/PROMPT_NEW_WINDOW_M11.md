# 新窗口启动提示词：M11 React 前端开发

> 使用方法：复制下面整段内容，作为新窗口的第一条消息发送。
> 前提：本窗口与后端窗口共用同一项目目录 D:\AI-Knowledge-Engine。

---

你是本项目的前端开发窗口。项目是"AI 深度报告本地知识检索系统"，后端（M0-M10）已全部完成并通过 Retrieval Quality Gate，现在由你独立负责 M11 React 前端开发。

## 必读（按顺序）

1. docs/HANDOFF_PROTOCOL.md —— 多窗口交接机制与硬约束
2. docs/HANDOFF_M11.md —— 你的任务契约：页面清单、后端 API 真实契约、功能细节、验收标准
3. docs/IMPLEMENTATION_STATUS.md —— 项目进度与 Known Issues

## 环境说明（不要重复初始化）

- 后端 API：127.0.0.1:8765（启动命令见 HANDOFF_M11.md §2.1；dev 语料库已 seed）
- Qdrant：Docker 容器 ai-kb-qdrant 应在运行
- 测试基线：.venv\Scripts\python.exe -m pytest backend\tests\ -q 应 102 passed
- Node.js / npm 已可用

## 任务

实现 M11 React 前端（React 18 + TypeScript + Vite + React Router + TanStack Query，UI 框架 Ant Design 或 Mantine 任选）：

1. /search 搜索页：搜索框 + Filters（Domain/Evidence/Content Type/Document）+ Mode 切换（Hybrid/Dense/Exact）+ Reranker/Debug 开关 + 结果卡片（Rank/标题/路径/Evidence 徽章/类型标签/摘要高亮/分数/行号）；
2. /document/:id 文档查看器：左侧 TOC 树 + 右侧 Markdown 分块渲染，搜索结果"查看上下文"跳转后按 start_line 滚动定位并高亮；
3. /index 索引状态页：四方计数与一致性、worker 健康、触发 scan / reindex；
4. /settings、/evaluation 页面（P1）。

API 契约以 docs/HANDOFF_M11.md §2 为准（字段已逐一核对），前端目录 frontend/ 新建于项目根，/api 代理到 127.0.0.1:8765。

## 执行纪律

- 先读文档再动手；后端代码不修改；API 契约变更需走后端窗口；
- 完成后运行 npm run build 验证 TS 无错、三页 P0 对接真实后端演示通过；
- 更新 docs/IMPLEMENTATION_STATUS.md（M11 状态 + 测试/构建结果）并 git commit；
- 按 docs/HANDOFF_PROTOCOL.md 的窗口结束流程收尾；
- 除非出现真正阻断，不要停下来询问，按里程碑推进。

现在开始：先按顺序读三份文档，然后搭建 frontend/ 工程骨架并实现 /search 页面。
