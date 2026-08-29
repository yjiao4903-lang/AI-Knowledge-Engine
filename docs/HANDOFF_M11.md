# M11 交接契约：React 前端开发

> 交接日期：2026-08-29 ｜ 交接方：后端窗口（M0-M10 已完成，最后 commit 见 git log）
> 接手方：前端开发窗口
> 开始前先读：`docs/HANDOFF_PROTOCOL.md`、`docs/IMPLEMENTATION_STATUS.md`

---

## 1. 任务定义（M11，spec §42-43）

实现 React + TypeScript 前端。**先做 Search / Document / Index Status 三个页面**，
Settings / Evaluation 页面其次。不做聊天页、不做 LLM Answer（V1 明确排除）。

### 页面清单与优先级

| 优先级 | 路由 | 内容 |
|---|---|---|
| P0 | `/search` | 搜索框 + Filters + Search Mode + Reranker/Debug 开关 + 结果卡片列表 |
| P0 | `/document/:id` | 左侧 TOC + 右侧 Markdown 渲染；点击搜索结果自动滚动到对应行/Section |
| P0 | `/index` | 索引状态（四方计数、一致性、worker 健康）、触发 scan / reindex |
| P1 | `/settings` | 展示 /api/settings 脱敏配置 |
| P1 | `/evaluation` | 展示 /api/evaluation/latest 指标表 |

### 技术栈（spec §43 锁定）

```text
React 18 + TypeScript + Vite
React Router（路由）
TanStack Query（数据获取/缓存）
UI 框架：Ant Design 或 Mantine 任选（不绑定）
Node.js/npm 已安装（M0 验证过）
```

### 工程位置与约定

```text
frontend/                # 新建于项目根（与 backend/ 平级）
frontend/src/pages/      # 页面组件
frontend/src/components/ # ResultCard、FiltersBar、TOC 等
frontend/src/api/        # 后端 API client（类型化）
frontend/src/types/      # API 响应 TS 类型
开发端口：Vite 默认 5173；/api 代理到 http://127.0.0.1:8765（vite.config.ts server.proxy）
```

---

## 2. 后端现状（不要改动，直接消费）

### 2.1 启动后端

```powershell
# 首次：seed dev 语料库（10 篇报告 -> data/catalog.db + Qdrant，已做过则跳过）
.venv\Scripts\python.exe backend\scripts\seed_dev_kb.py

# 启动 API（GPU worker 自动拉起，首次模型加载 ~30s）
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --port 8765
```

### 2.2 API 契约（真实响应字段，前端按此建模）

**POST /api/search** 请求：
```json
{
  "query": "HBM4 的接口位宽是多少？",
  "filters": {"document_ids": [], "evidence_levels": [1, 2], "content_types": []},
  "options": {"mode": "hybrid", "rerank": true, "top_k": 10, "debug": false}
}
```
mode ∈ hybrid | dense | lexical。filters 全部可选、空数组=不过滤。

响应：
```json
{
  "query": "...", "mode": "hybrid",
  "results": [{
    "rank": 1, "chunk_id": "M04:ch3-2:o1:0040", "document_id": "M04",
    "title": "……", "section_id": "M04:ch3-2:o1", "heading_path": "文档标题 > 第 3 章 > 3.2 …",
    "content_type": "table", "evidence_level": 1,
    "snippet": "……（约 200 字，查询词邻域）",
    "start_line": 395, "end_line": 401,
    "scores": {"dense_rank": 1, "terms_rank": null, "trigram_rank": 3,
               "rrf": 0.0246, "section_boost": 1.08, "final": 0.0265,
               "reranker": 0.992, "pre_rerank_rank": 2}
  }],
  "timing_ms": {"embed_ms": 0, "dense_ms": 0, "terms_ms": 0, "trigram_ms": 0,
                "fusion_ms": 0, "section_ms": 0, "rerank_ms": 0, "filter_ms": 0, "total_ms": 0},
  "debug": {"sources": {"dense": [], "terms": [], "trigram": []},
            "boosted_sections": [], "candidates_before_filter": 0, "fused_top": [], "rerank": [...]}
}
```
注意：
- `scores.reranker` / `pre_rerank_rank` 在 `options.rerank=false` 时为 null；
- `debug` 仅在 `options.debug=true` 时存在；
- 首次查询 embed_ms ≈ 1.3s（模型冷启动），之后 ~30ms + rerank ~1s；前端超时建议 ≥ 60s。

**GET /api/documents** → `{"documents": [{id, report_code, title, domain, status, completed_at, source_path, file_name, indexed_at}], "total": 10}`

**GET /api/documents/{id}** → 文档字段 + `chunk_count` / `section_count`；404 可能。

**GET /api/documents/{id}/sections** → `{"document_id", "sections": [{id, parent_section_id, level, heading, heading_path, section_type, ordinal, start_line, end_line}]}`（TOC 数据源，`parent_section_id` 为 null 表示顶层）。

**GET /api/chunks/{chunk_id}** → chunk 全字段（含 raw_markdown / plain_text / heading_path / start_line / end_line / title）。

**GET /api/index/status** → `{"counts": {documents, sections, chunks, fts_terms, fts_trigram, qdrant_points}, "consistent": bool, "last_full_scan", "inference_worker": {alive, device, device_kind, fallback_to_cpu, total_restarts}}`

**POST /api/index/scan**（无 body）→ 扫描并应用变更；**POST /api/index/reindex-document/{id}** → 重索引单文档。

**GET /api/settings** → 脱敏配置（含 fusion 权重、chunking 参数、query_instruction）。

**GET /api/evaluation/latest** → `{"results": {summary, per_type, gate, ...}, "report_markdown"}`。

错误格式：`{"error": "CODE", "message": "...", "detail": {}}`；404/400/403 见各端点。

---

## 3. 功能要求细节（spec §42）

### Result Card（搜索结果卡片）
必须显示：Rank、Title、Heading Path、Evidence（L1-L5 徽章，无标记显示 unmarked）、
Content Type（prose/table/causal_chain/... 用不同颜色标签）、Snippet（高亮查询词）、
Reranker/Final Score、Source Line（start_line-end_line）。
操作按钮：查看上下文（跳转 Document Viewer 并滚动到 start_line）、复制引用
（title + heading_path + chunk_id + 行号）。

### Document Viewer
- 左侧 TOC 树：按 `parent_section_id` 建树，`level` 缩进，`heading` 为节点文本；
- 右侧渲染文档：按 sections 的 `start_line/end_line` 分块渲染（chunk 内容用
  `GET /api/chunks/{id}` 或直接用 sections 数据 + Markdown 渲染器，如 react-markdown）；
- 从搜索结果跳转：`/document/M04?line=395` → 滚动到包含该行的 section 块并高亮；
- 原文操作：调用 `POST /api/documents/{id}/open-original` 用系统默认程序打开 .md。

### Search Page
- Filters：Domain（从 /api/documents 聚合）、Evidence 多选（1-5）、Content Type 多选、
  Document 多选（名称+代号）；全部映射到 request.filters；
- Mode 切换：Hybrid / Dense / Exact(lexical)；Reranker toggle；Debug toggle
  （Debug 开启时展示 timing 分解条 + 各路 rank）。

---

## 4. 验收标准（M11 Gate）

```text
[ ] npm run build 无 TS 错误
[ ] 三页 P0 全部可对接真实后端工作（非 mock）
[ ] 搜索 -> 查看上下文 -> 文档滚动定位 全链路可演示
[ ] Filters/Reranker toggle/Debug trace UI 生效
[ ] Index 页显示四方计数与一致性，能触发 scan
[ ] IMPLEMENTATION_STATUS.md 更新 + git commit
```

## 5. 已知注意事项

1. 后端仅绑定 127.0.0.1:8765，前端 Vite dev server 需代理（CORS 已天然规避）；
2. GPU worker 冷启动 30s + 首查 1.3s：UI 需有 loading 状态与优雅超时（≥60s）；
3. sections 表含文档根节点（ordinal 0，heading 为文档标题），TOC 建树时作为根；
4. chunk_id 格式 `{doc}:{section_id}:{ordinal:04d}`；section_id 带文档前缀（`M04:ch3-2:o1`），
   golden/前端跳转需用结果里的 `section_id` 与 `start_line`；
5. evidence_level 可能为 null（unmarked）；
6. 后端 API 若需要变更：先在后端窗口改 + 同步更新本文件的契约节 + 通知前端；
7. 测试基线：`.venv\Scripts\python.exe -m pytest backend\tests\ -q` 应 102 passed
   （前端窗口不修改后端时此数字只增不减）。
