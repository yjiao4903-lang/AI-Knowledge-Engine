# I4 交接契约：Unified Runtime（Window D）【已完成】

> 状态：**DONE（2026-08-30）** ｜ 交接方：Window C（I0-I3 Integration Lead）→ 执行方：Window D
> 依据：主计划 §38-42、补充方案 §31-33；I0-I3 已全部完成并归档
> 新窗口首读：本文件 → `D:\AI知识整合体系\docs\IMPLEMENTATION_STATUS.md` →
> `D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md`

## 完成记录（Window D，2026-08-30）

- 交付：`D:\AI知识整合体系\runtime\{common,start,stop,health}.ps1 + README.md + pids.json + config.integration-cpu.yaml`；
  两 Core 零改动；集成工作区（docs/runtime/integration_tests）首次入 git。
- **I4 Gate 全 PASS**：冷启动（Docker 已启 + Docker 未启两场景）、stop 干净不误杀（记录 PID 与
  端口发现两路径）、health 三态（PASS/WARN/FAIL）、GPU→CPU 降级演练（force_device=cpu → health WARN、
  产品可用）、Cognition 基线（unit 64/E2E 15/黑盒 10/10）、KE pytest dev 配置 114 passed。
- **发现的非回归问题**：KE 生产配置下 3 条 M5/M6 陈旧断言失败（dev 配置 114 全过；Golden 与 I0 逐位一致；
  见整合 Known Issues #14，I5+ ADR 候选）；CPU 降级 hybrid_rerank 超认知 5s 超时走 legacy fallback
  （设计内行为，见 #15）。**I4 Gate 判为完成**——两处均非 I4 改动引入，且按合约 I4 不改两 Core。
- 收尾：契约归档为本文件；I5 契约 `docs/HANDOFF_I5.md` + 启动提示词 `docs/PROMPT_NEW_WINDOW_I5.md`。

---

## 0. 继承资产与基线（已验证，勿重做）

| 资产 | 状态 |
|---|---|
| KE（D:\AI-Knowledge-Engine） | I0 完成：全量 189 篇 / 9780 chunks 一致性 PASS；config.yaml=生产全量（catalog_full.db + kb_*_full_v1）；pytest 114；commit `51d2e76` @ integration/research-os-v1 |
| cognition-app（E:\CODEX\AI深度研究\cognition-app） | I1-I3 完成：Retrieval Proxy + Reports 融合 + Evidence Bridge；unit 64 / E2E 15 / 黑盒 10/10；commit `7828306` @ integration/research-os-v1（baseline `cacf386`） |
| Integration Contract V1 | `D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md`（勿改 Identity 字段，改则先 ADR） |
| 跨系统黑盒 | `D:\AI知识整合体系\integration_tests\run.js`（10 场景，两服务在线时 `node run.js`） |
| 已知余量 | 全库 Golden MRR 0.765（阈 0.75）/ NDCG 0.801（阈 0.80）贴线；C03/R01/X01 为调参候选（须 ADR + A/B） |

服务启动（手工，I4 要自动化的就是这套）：
- Qdrant：Docker Desktop → 容器 `ai-kb-qdrant`
- KE：`D:\AI-Knowledge-Engine` 下 `.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8765`
- Cognition：`E:\CODEX\AI深度研究\cognition-app\start.bat`（必须复用，勿复制其逻辑；无 PATH Node 时它自动用 `%USERPROFILE%\.workbuddy\binaries\node\versions\*\node.exe`）

## 1. 任务范围（主计划 §38-42）

Runtime Workspace：`D:\AI知识整合体系\runtime\`（logs 同级 `D:\AI知识整合体系\logs\`）

### I4A start.ps1
1. 检查 Docker Desktop → 检查/启动 Qdrant（等待 /readyz）；
2. 检查 KE .venv 存在 → 启动 FastAPI（记录 PID 到 runtime\pids.json）→ 轮询 /api/health 直至 ok；
3. 启动 Cognition（调用真实 start.bat）→ 轮询 :3220；
4. 成功后打开浏览器 http://127.0.0.1:3220。

### I4B stop.ps1
- 按 pids.json 记录的 PID 停止 FastAPI 与 Cognition Node；
- **禁止** `taskkill /IM node.exe` / `/IM python.exe` 这类全局射杀；
- Qdrant 容器默认保留（加 `-Qdrant` 参数才停）。

### I4C health.ps1
- 检查 Docker/Qdrant、KE /api/health（含 gpu_worker 与 index_generation）、
  Cognition /api/retrieval/health（proxy 已汇总 KE 子状态）、:3220 主页；
- 输出逐项 PASS/WARN/FAIL + 汇总结论；退出码非 0 当 FAIL。

### I4D 故障策略与日志（主计划 §42/§46）
- GPU 失败 → KE 已内建 CPU fallback（产品仍可用，health 显示 WARN 即可）；
  Cognition 启动失败 → 整体 Startup FAIL（这是产品入口）；
- 整合层日志只记 startup/shutdown/health/跨系统故障，写
  `D:\AI知识整合体系\logs\integration-YYYYMMDD.log`，轮转 7-14 天；
- 两 Core 保留各自日志，不重复采集。

## 2. I4 Gate（主计划 §42 + 补充方案）

```text
[ ] start.ps1 一键从冷状态拉起全栈（Docker 未启动场景也要覆盖）
[ ] stop.ps1 干净停止且不误杀无关进程
[ ] health.ps1 三态输出正确（人为制造一个故障验证 WARN/FAIL）
[ ] GPU 失败降级路径演练（可临时 force_device=cpu 启 KE 验证）
[ ] Cognition 基线不下降（unit 64 / E2E 15 / 黑盒 10/10）
[ ] KE pytest 114 不下降（I4 不应改 KE 代码；如需改先 ADR）
```

### 可选加分项（补充方案 §34，时间允许再做）
- Golden Smoke Set：从 50 条 Golden 抽 ~10 条做成快速冒烟脚本
  （数据增量后只跑 Smoke；Embedding/Reranker/Chunker/权重变更才跑 Full）。

## 3. 硬约束（延续全部此前契约）

- 双库禁止合并；Retrieval 禁写认知；Proposal Gate 不可绕过；
- 不重写技术栈；ROCm 锁定 torch 2.9.1+rocm7.13.0；GPU 任务与测试严格串行（I0 事故教训）；
- 资源纪律：单进程串行验证，禁止并发跑索引/评测/测试套件；
- One-Writer：I4 期间 Window D 只写 runtime/ 脚本；改两 Core 需先在此契约登记理由；
- 交付格式（主计划 §64）：Code Changes / Files / Commands / Tests / Results /
  Known Issues / ADR / Commit / Next。
- 完成后：更新整合 IMPLEMENTATION_STATUS → 归档本契约 → 编写 I5（Backup/Hardening，
  主计划 §43-47：Tier1 认知 Markdown 必备份、Restore Drill 必须真实演练）契约。
