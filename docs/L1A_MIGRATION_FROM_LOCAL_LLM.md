# L1A Migration: From Local LLM to External TaskPack Worker

> 日期：2026-08-30 ｜ 依据：V3.0 实施方案 ｜ 状态：**已完成（架构侧）**，外部执行（Task 9/10）待用户进行。

---

## 1. 背景

原 L1A 方案在 Research OS 内部部署本地文本 LLM（Ollama + Qwen3-14B，实测 ~6.1 tok/s；
单条典型 55-175s、32 条全量约 2h）。V3.0 决策：**完全取消内部文本大模型运行时推理**，
模型能力外置，认知治理内置（§0/§2）。

## 2. 迁移了什么（本窗口已完成）

| 项目 | 说明 | 证据 |
|---|---|---|
| 移除生产 LLM runtime | Task 1：OllamaProvider 等离开生产路径，`tests/` 保留 MockProvider | commit 4a52308 |
| TaskPack V1 Schema | `backend/app/taskpack/schemas.py`（TaskYaml/Manifest/ResultEnvelope 等） | 4a52308 |
| TaskPack Builder + 模板 | `builder.py` + 落盘 `AGENT_INSTRUCTION_V1.md` / `OUTPUT_SCHEMA_V1.json` | b081fb3 |
| API + Importer/状态机 | `/api/synthesis/tasks*` 全套 + 八步 Gate + 状态机 | 0f4712d |
| Task Center 前端 | KE frontend `/tasks` + open-folder/prompt 端点 | a90f641 |
| 32 Golden → Golden TaskPack | `migrate_golden_taskpacks.py` + `taskpack_eval.py` | 48ddff1 |

## 3. 新的工作流

```text
Create TaskPack（outbox/）
  → 用户在外部工具打开任务目录并复制启动提示词（Task Center：打开目录 / 复制启动词）
  → 外部工具读包内 evidence.jsonl，调用其模型，写 result/result.json + result/DONE
  → KE Watcher/Importer 执行八步 Gate
  → 通过：COMPLETED（可查看 Draft）；失败：INVALID_RESULT
  → 用户审阅后 View Draft / Archive
```

## 4. 不再保留的内容

- Ollama / 本地 Qwen 文本生成 / 本地 LLM serving / GPU 文本推理调优；
- 嵌入式 model API 直接调用 runtime / 长连接等待生成（§0 明确取消列表）。

## 5. 对外部 Worker 的意义

- 模型选择自由：Trae / Codex / Qwen Code / Claude Code 等任何工具、任何模型；
- 唯一约束是 TaskPack 协议（输入输出格式），不关心 provider（§51）；
- 结果如何评估见 `TASKPACK_PROTOCOL_V1.md §9`。

## 6. 复现命令

```bash
# 生成 32 个 Golden TaskPack（幂等；需 KE catalog_full.db 就位）
.venv\Scripts\python.exe backend\scripts\migrate_golden_taskpacks.py

# 无模型评估某个 worker 的结果（runs 目录名）
.venv\Scripts\python.exe backend\scripts\taskpack_eval.py --runs runs/<worker>

# 回归
.venv\Scripts\python.exe -m pytest backend\tests\
```

## 7. 迁移前后对比

| 维度 | 迁移前（本地 Ollama） | 迁移后（External TaskPack） |
|---|---|---|
| 模型运行时 | Research OS 持有 | 外部工具持有 |
| 生成耗时 | 单条 55-175s（本地算力受限） | 取决于外部模型/服务 |
| 治理 | 内嵌 Guidance/Citation | TaskPack 协议 + 八步 Gate 内置 |
| 依赖 | GPU/ROCm/Ollama | 仅本地文件目录 |
| 可扩展 | 绑定单一模型 | 任意模型/工具可替换 |