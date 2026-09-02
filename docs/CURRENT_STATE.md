# AI-Knowledge-Engine Current State

更新日期：2026-09-02  
阶段：Research OS 实用化 / P1 研究质量增强

## 当前定位

```text
AI-Knowledge-Engine
= Evidence / Retrieval / TaskPack / Validation Engine
+ Research Workflow Host
```

Cognition App 仍是唯一正式认知写入者。

## 已完成

### Retrieval / Evidence
- Report Parser / Chunker / SQLite / FTS / Dense / Hybrid / Reranker；
- 全量报告索引与 Golden Regression；
- Cognition Markdown 只读派生索引，独立 catalog / Qdrant collection；
- Qdrant degraded 边界；
- 默认工作台改为 `lexical + rerank OFF`，语义/混合显式启用；
- Lexical metadata filter 已推进 FTS `LIMIT` 前，scoped search 不再因全库 Top-K 截断弱排名目标；
- Search Result 可加入 Evidence Basket；
- Basket 以 localStorage 持久化、按 `chunk_id` 去重；
- TaskPack Builder 仍从 catalog 权威解析 Evidence 正文。

### Personal Retrieval Feedback
- 新增本地 append-only 账本：`data/retrieval_feedback.jsonl`，不新增外部分析平台或云端依赖；
- 每次成功 `/api/search` 会生成独立 `search_id`，自动记录实际返回 Top-K 的 impression；
- impression 至少记录 `query / chunk_id / document_id / rank / mode / rerank / timestamp`；
- ResultCard 增加低干扰 `有用 / 无用` 反馈；
- `加入 Evidence / 移出 Evidence` 同步记录 `selected_as_evidence=true/false`；
- action 与 impression 通过同一 `search_id` 关联，便于后续按一次真实搜索还原排名与用户选择；
- 反馈账本由服务端写入 UTC timestamp，并带 `schema_version=1.0`；
- 搜索 impression 写入是 best-effort：反馈文件异常不会让搜索失败；
- 当前只采集数据，不自动调整 Dense/FTS/RRF/Reranker 参数，不做在线学习；
- Feedback 不属于正式 Cognition，也不会触发 Proposal / Apply / TaskPack mutation。

### Evidence Context Expansion
- TaskPack 创建支持 `none / neighbor_1 / section` 三种上下文模式；
- `none`：只使用用户在 Evidence Basket 显式选择的 anchor chunk；
- `neighbor_1`：按文档阅读顺序加入 anchor 前后各 1 个 chunk；
- `section`：加入 anchor 所在 section 的全部 chunk；
- 扩展仅发生在 TaskPack Builder / SQLite catalog 解析阶段，不触发新的 Search / Dense / LLM 调用；
- 扩展后的每个 Evidence 仍作为独立 `TaskPackEvidence` 行写入 `evidence.jsonl`，保留独立 `chunk_id / content_hash / section_id / line range`；
- 多 anchor 重叠上下文按 `chunk_id` deterministic 去重；
- 扩展后重新检查 `taskpack.max_evidence`，超限显式报错并清理半成品 TaskPack，不做静默截断；
- Search 工作台创建 TaskPack 时可直接选择上下文模式，默认仍为 `none`。

### TaskPack / External AI
- TaskPack V1 Builder / External Worker / Importer Gate；
- 结构化 `CognitionContextItem V1`；
- `Search -> Evidence Basket -> Create TaskPack` 已闭环；
- Task Center 可查看结构化 Result；
- INVALID_RESULT 可读但不可发布 Proposal。

### External Worker Launcher
- Task Center 的 READY 任务可直接选择固定 launcher：`codex / claude / terminal`；
- launcher 可用性只通过本机 PATH 探测，不从浏览器接受 executable、shell command、cwd 或 API key；
- Codex 使用非交互 `codex exec`，Claude Code 使用非交互 `claude -p`；两者只收到一条固定短指令，要求读取当前 TaskPack 的 `AGENT_INSTRUCTION.md`；
- 不把完整 TaskPack prompt 放进命令行，不在 KE 中嵌 OpenAI / Claude SDK，不保存模型凭证；
- 启动前 TaskPack 原子 `outbox -> processing`；supervisor 启动失败则回滚为 READY，避免任务无故卡在 PROCESSING；
- detached lifecycle supervisor 为 stdlib-only orchestration：等待外部 CLI 退出，根据 `result/DONE` / `result/FAILED` 把任务移动到 `completed/` / `failed/`；
- 外部进程退出但缺少 DONE/FAILED 时，写 `result/launcher_error.json` + `result/FAILED` 后进入 failed，避免假完成；
- Codex / Claude stdout、stderr 仅落本 TaskPack `result/launcher_stdout.log` / `launcher_stderr.log`，供本机排障；
- `Terminal` 只是本机 fallback shell；关闭后同样由 marker 判定 completed / failed；
- 原“启动词”复制与“打开目录”入口保留，Launcher 不可用时仍可手工执行 TaskPack；
- Launcher 不做 retrieval、不做 Result validation、不创建 Cognition Proposal、不执行 Apply，也不承担模型 Provider 职责。

### TaskPack Validation Cache
- Task Center 的 `GET /api/synthesis/tasks` 仍可触发 Importer scan，但已避免对未变化 COMPLETED TaskPack 重复执行完整 Gate；
- 缓存采用 TaskPack 本地 sidecar：`result/validation_cache.json`，不新增 SQLite migration；
- 缓存至少记录 `result_hash / validation_version / validated_at` 与完整 Gate report；
- 只有 `result_hash` 与 `validation_version` 同时匹配时才复用静态 Gate 结果；
- `result.json` 变化会自动失效缓存并重新执行完整 validation；
- validator 规则升级时通过 `validation_version` 自动失效旧缓存；
- 显式 `POST /api/synthesis/tasks/{task_id}/rescan` 永远绕过缓存并执行完整 Gate；
- catalog 可能独立变化，因此 cache hit 仍实时执行 stale-evidence Gate，避免缓存掩盖证据过期；
- 缓存文件损坏或格式非法时自动退化为完整 validation，不阻塞 Task Center；
- 原有 COMPLETED / INVALID_RESULT / IMPORTED 状态机保持不变，不新增“缓存状态”。

### Research Quality / Epistemic Review
- Deterministic Epistemic Linter 已接入 Proposal Candidate；
- `FORECAST_MARKED_SUPPORTED`：预测/估算/目标类 claim 标成 `supported` 时 warning；
- `CAUSAL_STRENGTH_UNDERGROUNDED`：claim 使用强因果，但引用 Evidence 快照没有显式强因果措辞时 warning；
- `TENSION_INSUFFICIENT_EVIDENCE_DIVERSITY`：tension 少于 2 条不同 Evidence 引用时 warning；
- Linter 仅提供 deterministic review warning，不做 semantic entailment；
- Linter 不修改 `ResultEnvelope`、Claim state，不把 warning 升级成 INVALID_RESULT；
- Warning 会进入 Proposal `warnings[]` 与 `[Research OS Review Warnings]` description 区块，供 Human Preview 复核。

### Cognition Integration
- TaskPack -> Cognition Proposal Candidate 保守转换；
- `supported` 不会升级为 `verified_fact`，仍固定映射为 Cognition `inference`；
- 新增 Cognition HTTP Gateway；
- KE 只允许调用 Cognition `POST /api/proposals` 创建 staging candidate；
- 新增 Proposal 发布幂等 marker：`result/proposal_publish.json`；
- KE 不暴露 Apply / Merge / Revision / Topic Update 能力；
- Task Center 可将通过 Gate 的结果发送到 Cognition Proposal 区；
- 正式变化继续由 Cognition Preview + Human Apply 完成。

### Runtime / Lifecycle
- Unified runtime / health / backup / restore 已迁入主仓；
- TaskPack 默认根 `<repo>/data/taskpacks`；
- 旧 TaskPack 安全迁移脚本；
- Cognition Markdown + durable TaskPack backup；
- Report watcher 与 Cognition watcher 已拆分职责，避免重复 cognition reconcile。

### CI
GitHub Actions：`.github/workflows/i8-ci.yml`

覆盖：
- Backend Research OS contracts；
- Retrieval regression / lexical metadata pre-filter regression；
- Personal Retrieval Feedback deterministic contracts；
- Deterministic Epistemic Linter unit + Proposal integration contracts；
- Evidence Context Expansion deterministic contracts；
- TaskPack Validation Cache deterministic contracts；
- External Worker Launcher lifecycle / fixed-command deterministic contracts；
- 前端 TypeScript/Vite build；
- Runtime PowerShell syntax。

CI 保持 lightweight：不安装本地 Embedding/Reranker 模型，不要求 Qdrant / ROCm / 真实 Cognition App，也不会真实调用 Codex / Claude 模型。

## 永久边界

```text
Cognition App = only formal cognition writer
KE = Evidence/TaskPack host + Proposal staging client
External Worker = synthesis executor
```

禁止：
- KE 直接写 Cognition Markdown；
- KE 调用 Proposal Apply；
- KE 调用 merge / revision / topic update 正式写接口；
- Report/Cognition SQLite 合并；
- Report/Cognition Qdrant collection 混用；
- TaskPack `supported` 自动映射 `verified_fact`；
- Evidence Context Expansion 拼接丢失 `chunk_id` 的匿名上下文；
- Evidence Context Expansion 隐式启动新的检索或模型调用；
- Validation Cache 跳过 catalog stale-evidence 检查；
- Validation Cache 改变 TaskPack 状态机或把旧 validation 结果当作永久事实；
- Retrieval Feedback 直接在线修改 retrieval 参数或自动训练排序器；
- Retrieval Feedback 写入失败阻断正常 Search；
- Retrieval Feedback 自动晋升为正式 Cognition；
- External Worker Launcher 接受浏览器传入的任意 executable / shell command / cwd / API key；
- External Worker Launcher 内嵌 OpenAI / Anthropic SDK 或变成模型 Provider；
- External Worker Launcher 绕过 TaskPack AGENT_INSTRUCTION / Evidence 边界；
- Epistemic Linter 自动改写 Claim state；
- AI output 自动晋升正式知识。

## 当前关键 API

```text
POST /api/search
POST /api/retrieval-feedback
POST /api/synthesis/tasks
GET  /api/synthesis/worker-launchers
POST /api/synthesis/tasks/{task_id}/launch-worker
GET  /api/synthesis/tasks
GET  /api/synthesis/tasks/{task_id}
GET  /api/synthesis/tasks/{task_id}/proposal-candidates
POST /api/synthesis/tasks/{task_id}/rescan

GET  /api/research-os/cognition/health
GET  /api/research-os/tasks/{task_id}/proposal-publication
POST /api/research-os/tasks/{task_id}/publish-proposal

GET  /api/taskpack/runs
GET  /api/health
```

## 当前用户路径

```text
关键词/语义/混合搜索
→ 自动记录 Top-K impression（仅本地 feedback ledger）
→ 可选标记 有用 / 无用
→ 选择 Anchor Evidence（同步记录 selected_as_evidence）
→ Evidence Basket
→ 选择 Evidence Context：none / neighbor_1 / section
→ 创建显式 chunk identity 的 TaskPack（READY）
→ Task Center 选择 Codex / Claude / Terminal Launcher（或继续手工启动）
→ processing/ + External Worker
→ DONE/FAILED + lifecycle supervisor
→ Importer Gate（未变化 Result 复用 Validation Cache；stale Gate 实时检查）
→ Result Viewer
→ Deterministic Epistemic Warning
→ 发送到 Cognition Proposal
→ Cognition Preview / Apply / Reject / Defer
```

## 运行配置

Cognition API：

```text
http://127.0.0.1:3220/api
```

环境覆盖：

```text
COGNITION_API_URL
COGNITION_DATA_ROOT
AIKE_TASKPACK_ROOT
AIKE_KB_ROOT
AIKE_MODEL_ROOT
AIKE_KE_PORT
```

本地非正式反馈数据：

```text
<paths.data_dir>/retrieval_feedback.jsonl
```

该文件是个人检索行为数据，不属于 Cognition 正式知识，不进入模型 prompt，不驱动实时排序。

## 仍需真机验收

GitHub Actions 无法代替本机：

- Windows + RX 7900 XTX / ROCm；
- 真实 Qdrant corpus；
- `E:\CODEX\AI深度研究\cognition-app`；
- 本机 `codex` / `claude` PATH 探测、已有登录状态与实际额度/权限；
- 真实 READY TaskPack 从 Launcher 启动后完整跑通 `processing -> completed/failed -> Importer Gate`；
- Terminal fallback 的新控制台行为；
- Cognition Proposal Preview / Apply；
- 旧 TaskPack 数据迁移；
- 真实长报告上的 `neighbor_1 / section` 上下文体量与研究体验；
- 大量历史 COMPLETED TaskPack 下 Task Center 轮询的实际 IO / latency 改善幅度；
- 至少约 100 次真实搜索后，检查 feedback ledger 的 impression / useful / Evidence-select 覆盖度与可分析性。

本机建议：

```powershell
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1
# 确认后
powershell -ExecutionPolicy Bypass -File .\runtime\migrate-taskpacks.ps1 -Apply

.venv\Scripts\python.exe -m pytest backend\tests\ -q
cd frontend; npm run build; cd ..
powershell -ExecutionPolicy Bypass -File .\runtime\health.ps1
.venv\Scripts\python.exe backend\scripts\integration_smoke.py
powershell -ExecutionPolicy Bypass -File .\runtime\backup.ps1 -VerifyAfter
```

## 下一批开发优先级

1. Task Center / Search 工作台的小型可用性优化：只基于真实使用痛点收敛，不做大规模 UI 重构；
2. Launcher 真机验收后再决定是否需要极少量 Windows 兼容修正，不在未验证前扩展为 Worker Scheduler；
3. Retrieval 参数调优：至少积累约 100 次真实搜索后，再基于 feedback ledger 评估 `dense_k / terms_k / trigram_k / RRF weights / reranker / chunk size`，当前阶段不提前调整。
