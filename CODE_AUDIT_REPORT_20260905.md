# AI-Knowledge-Engine 代码审计报告

- **审计对象**：https://github.com/yjiao4903-lang/AI-Knowledge-Engine
- **审计日期**：2026-09-05
- **审计方式**：全量源码人工审读（架构/质量 + 安全双线），关键结论经第二人交叉核实
- **规模**：约 13,700 行 Python（backend/app 约 7,100 行、tests 约 3,800 行、scripts 约 2,800 行）+ React 前端
- **综合评分**：代码质量 **7.5 / 10**，安全 **5 / 10**（按联网标准；纯本机使用约 7.5/10）

---

## 一、项目概览

单机本地知识检索引擎：面向中文投研 Markdown 语料的解析 → 分块 → 索引（SQLite FTS5 + Qdrant 双索引）→ 混合检索（dense + FTS terms/trigram + weighted RRF 融合 + 可选 Reranker）→ 证据接地合成，外加 TaskPack 外部 Worker 协议与 cognition 第二语料路线。

- **技术栈**：Python 3.12 + FastAPI + pydantic v2 + SQLite（WAL/FTS5）+ Qdrant + sentence-transformers（Qwen3-Embedding/Reranker-0.6B，ROCm torch）+ jieba + markdown-it 自研解析器。依赖在 `requirements-lock.txt` 全量锁定。
- **数据流**：知识源(只读 md) → scanner（增量 manifest，size+mtime 快路径 / sha256 慢路径）→ docid_policy（收录/排除/消歧）→ IndexPipeline（staging 全内存 → SQLite 单事务原子替换 → Qdrant delete+upsert）→ 检索（Qdrant + FTS → RRF 融合 → parent boost → 过滤 → 重排）→ API；推理在独立 spawn Worker 进程中执行，watchdog 连续崩溃自动降级 CPU。
- **分层**：core → parser → chunking → lexical/retrieval → indexing → api，无循环依赖，`main.create_app` 手工装配，依赖方向单向。

## 二、亮点

1. **索引一致性设计成熟**：staging → SQLite 单事务原子替换（`backend/app/indexing/pipeline.py:152-163`）→ Qdrant 替换 → reconcile 兜底；删除走 tombstone，改名按 sha256 识别零重嵌入；"staging 失败旧版本继续可搜"的不变量有测试锁定（`backend/tests/test_indexing.py:117`）。
2. **推理进程隔离 + 自愈**：GPU 推理独立进程 + watchdog + 连续 2 次崩溃自动降级 CPU + runtime_profile 持久化（`inference/manager.py:139-167`），对 Windows ROCm 的 0xC0000005 崩溃场景有完整文档化策略。
3. **错误模型规范**：`core/errors.py` 全量显式错误分类（code + http_status），AppError 全局 handler 输出结构化 JSON，几乎无裸 `except: pass`。
4. **TaskPack 外部边界协议严谨**：全版本化 Schema、manifest sha256 不可变清单、八步导入 Gate、失败原子清理、归档强制同卷原子 rename 拒绝覆盖（`taskpack/importer.py:520-536`）——全库质量最高的模块。
5. **确定性 ID 与可复现性**：chunk_id 结构化、Qdrant point 用 uuid5 确定性映射、doc_id 策略含 canonical 排序与全量排除原因审计。
6. **文档与代码互证**：docstring 引用 spec 条款编号，docs/ 有完整里程碑 handoff 与评测报告（m9_eval 七臂消融），commit 纪律好。
7. **安全微观工程扎实**：SQL 全参数化（FTS MATCH 表达式经 `_quote` 安全包裹）；`os.startfile` 双端点有 resolve+白名单 fail-closed 校验；全仓库无 subprocess/eval/pickle/yaml.load 危险调用，YAML 全部 safe_load；无硬编码机密。

## 三、问题清单

### P0（严重）

**P0-1 查询侧推理绕过 Worker 进程隔离，API 主进程常驻加载完整 embedding 模型**（已核实）
- 位置：`backend/app/retrieval/dense.py:56-62`、`dense.py:159`、`backend/app/main.py:71`
- 证据：`DenseRetriever.__init__` 在 FastAPI 主进程内 `from_pretrained(...).to(device)` 加载 Qwen3-Embedding，查询向量在 API 进程内推理；而文档嵌入与 rerank 均经 Worker 隔离。
- 影响：API 主进程直接跑 ROCm torch 恰是该项目自己记录的最易触发 0xC0000005 崩溃的路径——一旦崩溃整个后端（检索/索引/TaskPack 全部服务）死亡且无自愈；同时 GPU 显存双份占用、启动时间翻倍、双进程并发抢 GPU。
- 修复：查询向量化统一改走 `manager.call("embed_query", ...)`（Worker 协议已定义该任务类型），删除主进程内 `TorchEmbeddingProvider`。

### P1（重要）

1. **`/api/index/rebuild` 后 LexicalSearcher 持有已关闭的旧连接，hybrid/lexical 检索全量 500 直到重启**（已核实）——`api/index.py:83-93` 只替换了 `engine.conn`/`pipeline.conn`，`SearchEngine.__init__` 里 `self.lexical = LexicalSearcher(conn)` 另持一份引用未更新；此后 `mode=hybrid/lexical` 的搜索全部抛 `Cannot operate on a closed database`。修复：为 SearchEngine 提供 `set_conn()` 或改为经 `app.state` 的访问器。
2. **单个 SQLite 连接跨线程共享，事务中途可被读线程"搭车"产生脏读**——`main.py:48` `check_same_thread=False` 的单连接既被 watcher 写线程的 `with self.conn:` 事务使用，又被全部 API 读线程直接 SELECT；索引事务中间态可被读请求看见，破坏"旧版本始终可搜、新版本原子可见"的设计目标，也浪费了 WAL。修复：API 读侧用独立只读连接（thread-local 或每请求）。
3. **`manager.health()` 会被长推理任务阻塞**——`inference/manager.py:111-112` 的 `call` 全程持 `_lock`，timeout 在拿到锁之后才计时；全量索引期间 `/api/index/status` 的 health 探测可挂起数分钟。修复：health 改为纯状态读取（is_alive + 心跳时间戳）。
4. **Cognition 路线大面积复制 IndexPipeline/Scanner（约 250 行近似重复）**——`cognition/pipeline.py:74-224` vs `indexing/pipeline.py:53-259`；任一侧修 bug 另一侧极易漏改，且 cognition 侧缺 docid_policy/排除审计。修复：抽取公共管道，注入 doc_id 策略/collection 三个差异点。
5. **测试与开发机强耦合、无 CI**——`tests/conftest.py:36-89` 连真实 Qdrant `127.0.0.1:6333` 与真实本地模型；检索/索引/API 层测试实为本机集成测试，环境缺失时表现为大面积 error 而非优雅 skip（`test_search_engine.py:14` 的 `if fixture is None: skip` 是死分支）。仓库无任何 CI。修复：纯逻辑测试拆 CI 层，集成层标记 `@pytest.mark.integration` 默认 skip。

### P2（一般）

1. **Qdrant 差异修复（reconcile.repair）只有 CLI 入口，watcher 不自动执行**（`indexing/reconcile.py:49-118`）——SQLite 提交后 Qdrant 写失败导致的缺点/孤儿会持续到人工跑 `reindex.py repair`，期间 dense 召回静默缺失。
2. **`docid_policy` 文档与实现漂移**——`docid_policy.py:61-63` 实际把收录范围硬性收窄为 stem 含"最终报告"的文件，docstring 未声明；`^(M\d{1,2})_` 规则在非"最终报告"时永不生效。
3. **检索 `mode` 参数未做枚举校验**（`api/search.py:21`）——拼错的 mode 静默返回 200 + 空结果。改 `Literal["dense","lexical","hybrid"]`。
4. **日志无轮转 + `setup_logging` 早退分支可能丢失文件 handler**（`core/logging.py:30-40`）——`app.jsonl` 无上限增长；root handler 已存在时 JSON 文件日志静默不生效。
5. **`GET /api/synthesis/tasks` 带写副作用（触发 Importer scan）且 scan 无并发保护**（`api/synthesis.py:119`、`taskpack/importer.py:434-451`）——违反 GET 语义，并发轮询会重复 scan；至少加模块级锁。
6. **`parser_version` 字面量 `"0.1.0"` 散落三处**（`indexing/pipeline.py:90`、`cognition/pipeline.py:106`、`lexical/corpus.py:60`）——将来 parser 升版改不全会导致增量 reconcile 误判。

### P3（建议，摘要）

- `manager._pending` 死代码；`importer.py:257` 的 `_gate_manifest` 死条件（两分支相同）；`m9_eval.py:74` 永假表达式等脚本调试残留。
- `reconcile.py:108` 用 `split(":")` 反推 section_id 对含 `:` 的 cognition doc_id 会得错结果（埋雷）。
- `rerank.py:44` `if pos > 0` 应为 `>= 0`；`markdown_parser.py:72` 循环内重建集合 O(n²)；snippet 宽度等魔法数字应入配置。
- `requirements-lock.txt:2` 内嵌历史绝对路径 `-e d:\ai-knowledge-engine\backend`，换机不可复用；`config.py:212-213` 配置缺失时静默退回 `D:/`、`E:/` 默认值应至少告警。
- 测试死角：watcher 生命周期、rebuild 后检索状态（正好漏掉 P1-1）无覆盖；NDCG/MRR 在 `api/evaluation.py` 与 `m9_eval.py` 重复实现两份。

### 安全问题（按联网标准）

| 级别 | 问题 | 位置 | 说明 |
|---|---|---|---|
| Critical | 全部 API 零认证零授权 | `main.py:186-193` | 无任何鉴权中间件；绑定地址 `127.0.0.1` 仅为可配置默认值（`bind_host`）。暴露到网络即：读全部私有研究语料、枚举本地路径、触发重建 |
| High | `/api/index/rebuild` 无凭据删除整个 SQLite 库 | `api/index.py:74-91` | 唯一"防护"是客户端自传 `confirm:"yes"`，非认证 |
| High | 无速率限制、无 body 大小限制 | `api/index.py:41-55`、`evaluation.py:51-89` | 循环打 `/api/index/scan` 即可让 CPU/磁盘满载并阻塞全部检索 |
| Medium | 无 CSRF/Host 校验（DNS rebinding 可行） | `main.py` 全文无中间件 | 恶意网页可无预检 POST 驱动写端点；rebinding 后可读取全部 GET 响应（私有知识库内容外泄） |
| Medium | `os.startfile` 双端点按扩展名关联执行 | `documents.py:100`、`synthesis.py:188` | 路径穿越已防住（resolve+白名单 fail-closed）；剩余风险是 roots 配置过宽 + CSRF 组合可远程打开任意关联程序 |
| Medium | 信息泄漏 | `documents.py:13-19`、`settings.py:10-23`、`index.py:30-31` | 响应含本地绝对路径、完整配置快照、Qdrant 错误原文 |
| Low | `/docs`、`/openapi.json` 默认开启；真实目录结构随 `config/config.yaml` 入库 git | `main.py:186` | 公网仓库会暴露个人目录结构与设备信息（无凭据泄漏） |

**已核实干净项**：SQL 注入（全参数化 + FTS 语法转义）、路径穿越/zip slip（无上传端点，taskpack 导入有 run_id 白名单 + 八步 sha256 Gate）、SSRF（无出站 HTTP）、命令注入/反序列化（grep 零命中）、依赖版本（Jinja2/urllib3/h11/torch 均在已知严重 CVE 修复线之上；建议上线前跑一次 `pip-audit`）。

## 四、测试与工程实践

约 230 个测试用例 / 3.8k 行。**纯逻辑层（TaskPack 八步 Gate、synthesis 校验、parser/chunker、docid_policy、lexical 查询解析）密闭且质量高**，断言具体、故障注入手法成熟。短板：检索/索引/API 层是事实上的本机集成测试（真实 Qdrant + GPU 模型），无 CI、无分层标记；watcher/rebuild 后状态等"胶水层"零覆盖。工程侧 docs/ 驱动的里程碑制、handoff 与评测报告文化出色，但 ruff 有配置无执行、无 lint/test CI、lock 文件含陈旧绝对路径——工程化"最后一公里"未闭环。

## 五、总体结论

**7.5 / 10（质量）｜ 5 / 10（安全，联网标准）** —— 领域设计（索引一致性、错误模型、TaskPack 协议、确定性 ID）达到优秀水准，文档纪律罕见地好；但查询侧推理绕过 Worker 隔离（P0-1）、rebuild 后检索瘫痪（P1-1）、共享连接跨线程脏读（P1-2）三个问题削弱了其引以为傲的可用性设计。当作 127.0.0.1 个人工具安全可接受；**任何联网/端口转发/反代之前必须先补认证 + 破坏性端点防护 + 限流**。

### 优先行动清单

1. 查询向量化改走 Worker（P0-1）——消除主进程崩溃单点。
2. 修 rebuild 后的连接引用（P1-1）与共享连接脏读（P1-2）。
3. 加最小鉴权中间件（X-API-Token）+ TrustedHost + 限流 + body 大小上限；rebuild/scan 要求独立凭据。
4. 建 CI：至少把纯逻辑测试（taskpack/synthesis/parser/lexical）跑起来；集成测试加 marker。
5. reconcile.repair 低频自动化；补 `PARSER_VERSION` 常量与 `mode` 枚举校验。
