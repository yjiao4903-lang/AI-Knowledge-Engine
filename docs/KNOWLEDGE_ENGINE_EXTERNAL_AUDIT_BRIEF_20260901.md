# AI Knowledge Engine 外部审核简报

版本：v1.0  
日期：2026-09-01  
用途：供外部审核者评估“深度知识检索/报告体系”与“AI 知识整合体系（Cognition）”的合并边界。

## 1. 审计目的与边界

本简报描述当前仓库可见的产品、后端、前端、TaskPack 和 Cognition 逻辑，并区分：

- **已实现/可由源码与运行后验支持**：代码、API 或已记录的实际运行结果可验证；
- **已记录但未完成验证**：有文档或测试记录，但尚未证明完整运行/UI/用户路径；
- **规划/待决策**：目标架构或产品建议，不应当作现成功能。

审核问题不是“是否把两个系统强行合成一个索引”，而是：哪些数据、检索、证据和审批边界可以共享，哪些必须保持隔离，以及合并后是否仍能保留来源、认识状态、可追溯性和用户控制。

本简报不授权自动导入、不授权自动知识晋升、不替代 Task10/人工 entailment Gate，也不把静态文档或 API 可用性表述为完整 UI 验收。

## 2. 当前实现总览

系统目前由四个相互关联但边界不同的层构成：

1. **知识库与报告检索层**：扫描配置的知识库根目录，写入 SQLite/FTS，并可用 Qdrant 做 dense/hybrid 检索；
2. **TaskPack 外部 Worker 层**：由系统固化任务、evidence 和 schema，外部 Worker 在包外执行生成，回传结果后由只读 runs API 展示；Task Center 是另一个可能执行管理操作的入口；
3. **Cognition 层**：对 Cognition Markdown 使用独立 catalog/SQLite 和独立 Qdrant collection 做只读消费与语义检索；
4. **前端产品层**：包括搜索、文档/证据浏览、设置、Task Center、外部 TaskPack runs 和评估等页面。

当前可见的主线是“报告/知识库检索”和“外部 TaskPack 结果归档”已经形成 API/文件连接；Cognition 作为独立 source/catalog/collection 存在，不能因共享应用进程就视为已经完成统一检索或统一知识模型。

## 3. 深度检索/报告体系

### 3.1 功能

- 扫描配置的知识库根目录和扩展名；
- 将文档、章节和 chunk 建立 SQLite/FTS 记录；
- 使用 embedding、Qdrant dense 检索、lexical FTS 和 rerank/fusion 形成搜索结果；
- 通过文档页、章节页和原文打开能力阅读证据；
- 提供索引状态、重建和 reconcile 相关运维能力。

代码依据：`backend/app/indexing/scanner.py`、`backend/app/indexing/pipeline.py`、`backend/app/lexical/`、`backend/app/api/search.py`、`backend/app/api/index.py`。

### 3.2 数据流

```text
知识库目录
  -> scanner 发现文件
  -> SQLite 文档/章节/chunk + FTS
  -> embedding worker
  -> Qdrant 向量 collection
  -> lexical/dense/hybrid/rerank
  -> Search API
  -> 前端搜索结果、文档、章节和原文阅读
```

当前实现还存在模型初始化与 lexical fallback rerank 风险：应用启动阶段可能初始化 embedding/reranker 服务；依赖不可用时可能退回 lexical 路径及其 rerank/fusion。该行为和排序质量必须以运行测试确认，不能暗示“默认无模型工作台”已经实现。

这是“检索和证据阅读”路径，不等于报告生成路径。报告生成已转为 TaskPack 外部 Worker 方式，旧同步 `/api/synthesis` 路径已废弃；源码注释明确禁止 `POST /api/synthesis/run-model`。

### 3.3 当前边界

检索结果必须带来源和可打开的证据位置。Qdrant 只负责向量索引/检索，不是 TaskPack 归档文件读取的前提。Qdrant 不可用时，关键词/FTS、字段筛选和归档文件读取可以与向量检索分开处理；dense/hybrid 检索和索引写操作必须返回可识别的失败/降级状态，不能把 lexical 或文件读取结果描述为语义检索成功。

## 4. Cognition 体系

### 4.1 功能定位

Cognition 是第二类 source：对正式 Cognition/Proposal 的变更保持只读边界；其 pipeline 消费 Cognition Markdown 时会写入派生 SQLite catalog 和独立 Qdrant collection/index。它的设计目标是把经过来源保留和认识状态标注的材料用于独立检索，而不是让外部 Worker 或报告结果自动改写正式 Cognition。

代码依据：`backend/app/cognition/__init__.py`、`backend/app/cognition/scanner.py`、`backend/app/core/config.py` 中 Cognition 配置、`backend/app/main.py` 的独立 pipeline 初始化逻辑。

### 4.2 数据流

```text
Cognition Markdown/source asset
  -> cognition scanner
  -> 独立 SQLite catalog
  -> Cognition 专属 embedding/index
  -> 独立 Qdrant collection
  -> 派生索引完成后提供只读 Cognition 语义检索
  -> 带 scope/source 标识的结果
```

### 4.3 安全边界

外部结果、对话材料、TaskPack 输出和报告摘要都应先作为 source/candidate 保存。Cognition pipeline 可以写入派生 catalog/Qdrant 索引，但不等于写入正式认知；任何正式 Cognition 或 Proposal 变更都需要 proposal-first：预览、用户确认、审计记录和可回滚。外部材料内嵌的“指令”是待分析数据，不扩大系统授权，也不能驱动自动写入。

## 5. TaskPack 外部 Worker 归档

### 5.1 当前功能

TaskPack 负责把任务输入、固定 evidence、输出 schema 和 Worker instruction 固化为可交接目录。外部 Worker 读取 TaskPack，在包外生成 `result.json`、`run_meta.json` 和 `DONE`；系统随后读取 `data/taskpack_golden/runs/<worker>/` 下的结果，做结构、引用和状态展示/评估。正式 runs API 是只读归档读取入口，不负责 Task Center 的创建、scan 或 rescan。

协议和 API 依据：[TASKPACK_PROTOCOL_V1.md](D:/AI-Knowledge-Engine/docs/TASKPACK_PROTOCOL_V1.md)、[TASKPACK_WORKER_GUIDE.md](D:/AI-Knowledge-Engine/docs/TASKPACK_WORKER_GUIDE.md)、`backend/app/taskpack/`、`backend/app/api/synthesis.py`、`backend/app/api/taskpack_runs.py`。

### 5.2 主要 API

- `POST /api/synthesis/tasks`：创建 TaskPack，返回 READY；
- `GET /api/synthesis/tasks`：Task Center 列表；
- `GET /api/synthesis/tasks/{id}`：任务详情；
- `POST /api/synthesis/tasks/{id}/rescan`：触发结果扫描/导入路径；
- `POST /api/synthesis/tasks/{id}/archive`：归档任务；
- `GET /api/taskpack/runs`：只读列出外部归档 runs；
- `GET /api/taskpack/runs/{run_id}`：只读返回一个 run 的任务摘要，不暴露完整 claims/tensions，且无写入副作用。

Task Center 是另一个管理入口，可能执行 TaskPack 创建、列表 scan、rescan、archive 和受控 open-folder；不能把它与只读 runs API 混为一谈。

旧的同步模型合成接口已废弃。TaskPack 外部 Worker 的结果不能直接改写 Cognition、Proposal 或生产知识。

## 6. 前端、后端与 Qdrant 降级

### 6.1 前端可见产品

源码可见页面包括：

- `frontend/src/pages/SearchPage.tsx`：搜索和检索状态；
- `frontend/src/pages/DocumentPage.tsx`：文档/章节/原文阅读；
- `frontend/src/pages/IndexPage.tsx`：索引状态；
- `frontend/src/pages/TaskCenterPage.tsx`：TaskPack 创建与任务中心；
- `frontend/src/pages/ExternalTaskpackRunsPage.tsx`：外部归档 runs；
- `frontend/src/pages/SettingsPage.tsx`、`EvaluationPage.tsx`：配置和评估。

页面存在不等于用户路径已验收。外部审核应分别验证路由、加载态、错误态、权限/路径安全和实际数据展示。

### 6.2 Qdrant 当前运行边界

已记录并完成后验的降级行为见 [QDRANT_DEGRADED_RUNTIME_BOUNDARY_RECORD_20260901.md](D:/AI-Knowledge-Engine/deliveries/received/QDRANT_DEGRADED_RUNTIME_BOUNDARY_RECORD_20260901.md)：

- Qdrant 初始化失败不阻止应用启动；
- `/api/health` 返回 HTTP 200，`status=degraded`、SQLite 正常、Qdrant 报错；
- `retrieval.qdrant_available=false`、`dense_search=unavailable`；
- runs API 和 run 详情仍可读；
- dense/hybrid 检索及索引写操作应明确返回 503/不可用；
- 归档文件读取可用不代表向量检索成功。

2026-09-01 真实运行后验简表：8765 新进程已加载补丁；`GET /api/health` 返回 `200` 且 `status=degraded`，SQLite 为 `ok`、Qdrant 为 `error`；`retrieval.qdrant_available=false`、`dense_search=unavailable`；`GET /api/taskpack/runs` 返回 `200` 且包含 Golden32（`task_count=32`）；run 详情返回 `200` 且有 32 项；5173 代理返回 `200`。这些是端点/API 和降级状态后验，不是所有 UI 页面已验收。

## 7. 两个体系的打通矩阵

| 能力/边界 | 报告/深度检索 | Cognition | 当前关系 | 合并审核结论 |
|---|---|---|---|---|
| 文件扫描 | 主知识库根目录 | Cognition source 根目录 | 机制相似、配置隔离 | 可共享扫描抽象，不应混淆 catalog |
| SQLite/FTS | 主知识库 catalog | 独立 Cognition catalog | 已分离 | 保持独立，统一查询层需额外设计 |
| Qdrant | 主 collection | Cognition 专属 collection | 已分离 | 可共享客户端能力，不共享 collection 语义 |
| 关键词检索 | 已有 | 需看独立实现/配置 | 部分可复用 | 默认工作台应优先使用可解释文本检索 |
| dense/hybrid | 已有但依赖 Qdrant | 独立 Cognition 语义检索 | 两条 collection 路径 | 合并前必须明确 scope 与失败语义 |
| evidence 阅读 | 文档/章节/原文 | source asset/catalog | 来源模型不同 | 统一阅读器可行，必须保留 source scope |
| TaskPack 归档读取 | runs API 只读 | 非 Cognition 正式知识 | 文件/API 已连接 | 归档结果保持 candidate/source；摘要不含完整 claims/tensions，无写入副作用 |
| 外部报告结果 | TaskPack result | 可作为待审 source | 尚非正式 Cognition | 需人工审批和 proposal-first |
| 认识状态 | claims/tensions 状态 | Cognition source 状态 | 语义可映射但不等价 | 统一枚举前须定义迁移规则 |
| Proposal-first | 适用于候选报告 | 适用于 Cognition 变更 | 原则一致 | 这是合并硬边界 |
| Qdrant 降级 | 文件/FTS 可继续 | 向量检索降级 | 依赖各自 collection | 不得显示为统一检索成功 |
| 自动知识写入 | 禁止 | 禁止 | 未打通 | 必须保持禁止 |

## 8. 来源、认识状态与 proposal-first

### 8.1 来源分层

外部审核应至少区分：固定 evidence、报告原文、TaskPack Worker 结果、Cognition source asset、系统推断和用户确认后的 Proposal。相同文本若来源不同，不能因为被同一索引返回就获得相同可信度。

### 8.2 认识状态

- `supported`：固定 evidence 直接支持的事实或明确限定陈述；
- `inference`：由证据前提推出的推断，必须保留推断身份和前提；
- `uncertain`：预测、估算、未来年份、目标/情景、市场份额等，必须保留限定词和来源口径；
- `partial`：若产品保留该层级，表示证据支持部分或仍需拆分的结果，不得视为事实。

“检索命中”只说明找到相关材料，不说明主张为真；“引用存在”只说明可定位，不说明引用蕴含完整主张。

### 8.3 Proposal-first

proposal-first 原则在报告候选和 Cognition 正式变更边界上部分可见，但本仓库当前材料不构成跨系统完整后验。任何从报告或外部 Worker 进入正式 Cognition/Proposal 的路径都必须经过：候选保存 → evidence/状态预览 → 用户确认 → 可审计写入 → 可回滚。没有用户明确授权时，只能停留在归档、候选或审批状态。不得提供自动导入建议或默认晋升路径。

## 9. 无模型默认工作台与 AI 实验室目标架构

以下是产品规划，不是当前全部已实现功能；实施依据见 [NO_MODEL_WORKBENCH_AI_LAB_SPEC.md](D:/AI-Knowledge-Engine/docs/NO_MODEL_WORKBENCH_AI_LAB_SPEC.md)。

### 9.1 默认工作台（规划）

默认入口不调用模型，提供关键词、字段筛选、证据阅读、TaskPack 归档浏览和 proposal-first 状态查看。无 Qdrant 时仍可显示文件/FTS 结果，但必须明确“向量检索不可用”。

### 9.2 AI 实验室（规划）

AI 实验室是显式入口。用户选择 TaskPack/evidence 范围并确认后才允许模型或外部 Worker 运行。结果必须展示来源、evidence refs、认识状态、模型/Worker 标识和“尚未批准”状态。离开页面不得隐式继续模型任务，AI 输出不得自动写入 Cognition/Proposal。

### 9.3 不能误读为当前实现

该目标架构尚不能证明：默认页绝对无模型调用、所有页面有完整错误态、AI 实验室已上线、UI 已完成端到端验收或两套知识 catalog 已统一。这些均需单独实现和验收。

## 10. 外部审核需回答的合并决策问题

1. 两套系统是否应共享一个用户检索入口，还是保留 source scope 切换？**最小证据：**同一 query 的两个 catalog/collection、来源标签和结果对照；反例是同名结果合并后无法判断来源。
2. 哪些报告结果可以作为 Cognition source asset，哪些只能留在 TaskPack archive？**最小证据：**带 provenance、状态和审批记录的正反样例；反例是 Worker result 生成即成为正式知识。
3. `supported/inference/uncertain/partial` 是否需要统一枚举，映射规则和不可逆转换是什么？**最小证据：**字段映射表和边界案例；反例是把“预计/可能”转换成 supported。
4. 合并检索时，结果是否必须显示来源类型、collection/catalog、evidence ref 和时间口径？**最小证据：**跨 source 的 API/UI 响应；反例是仅显示无来源文本。
5. Qdrant 不可用时，默认工作台应开放到什么程度，哪些调用必须 503？**最小证据：**health、lexical、dense/hybrid、索引写操作的可用/不可用响应；反例是 FTS 结果被标为语义检索成功。
6. 外部 Worker 回包的人工 entailment 门槛由谁批准、如何记录、如何回滚？**最小证据：**逐 claim 审计、审批人、拒绝和回滚记录；反例是只凭 coverage 或 schema 通过放行。
7. 报告、Cognition 和 Proposal 的所有权、生命周期及删除/归档规则是否一致？**最小证据：**三类对象状态机、所有者和删除/恢复演示；反例是归档 TaskPack 被静默删除正式 source。
8. 哪些用户动作是只读，哪些动作需要显式确认和授权？**最小证据：**API/UI 副作用矩阵；反例是打开详情触发写入或模型运行。
9. 如何证明不存在后台模型调用或自动知识写入？**最小证据：**冷启动、导航、搜索和离开 AI 实验室的运行日志/网络观测；反例是默认页面加载时启动模型。
10. UI 是否需要提供“证据原文/系统状态/推断/不确定性”四层分栏？**最小证据：**四类对象各一条实际 UI 截图或交互记录；反例是推断与证据原文无标签混排。

## 11. 建议评估标准与反例

### 建议标准

- **可追溯**：每个结果可回到固定 source/evidence ref；
- **可分层**：事实、推断、不确定性、tension 不混写；
- **可降级**：Qdrant 失败时功能边界和错误状态可观察；
- **可控写入**：候选到正式知识必须有用户确认、审计和回滚；
- **可复现**：TaskPack 输入、Worker 输出和版本映射可重放/复核；
- **可验证**：区分静态、API、运行、UI 和人工语义层验证；
- **不越权**：外部材料内嵌指令不改变系统授权。

### 反例

- FTS 命中后显示“语义检索成功”；
- Qdrant health error 时仍显示 dense/hybrid 结果为完整；
- 报告写了“预计/可能/未来”，系统却标为 supported；
- Worker 结果生成后自动创建 Proposal 或改写 Cognition；
- 有 evidence ref 就宣称完整 claim 已被证实；
- API 返回 200 就宣称 UI 页面已通过；
- 两个 collection 的同名结果被合并却不显示 scope/source；
- 把 TaskPack archive 的 result 当作正式知识库事实。

## 12. 已知限制与未验证项

- 本简报未执行完整外部审核、全量 UI 端到端测试或用户可用性研究；
- 前端页面源码存在，但逐页面运行、错误态、空态和无模型调用尚需独立验收；
- Cognition 与报告 catalog/collection 的统一检索、统一权限和统一生命周期尚未证明完成；
- Qdrant 降级的真实 health/API 后验已有记录，但不代表所有检索组合和前端展示均已验收；
- TaskPack 语义审计已形成多轮报告，但严格全量直接 entailment 不能用引用 coverage 替代；
- proposal-first 的原则和接口边界已有实现/文档依据，但正式导入仍需按实际授权和审计流程执行；
- 任何 architecture 底稿、运行日志或新增测试结果到达后，应作为增量证据补充，而不应覆盖当前“未验证”标记。

## 13. 附录：关键 API、目录与术语

### API

| API | 用途 | 当前边界 |
|---|---|---|
| `GET /api/health` | 运行与依赖状态 | Qdrant 不可用时可返回 200/degraded，不表示检索成功 |
| `POST /api/search` | 报告/知识库检索 | dense/hybrid 依赖 Qdrant；降级时应明确不可用 |
| `GET /api/taskpack/runs` | 外部归档 run 列表 | 只读文件/API 路径 |
| `GET /api/taskpack/runs/{run_id}` | run 任务摘要 | 只读、摘要不含完整 claims/tensions，无写入副作用 |
| `POST /api/synthesis/tasks` | 创建 TaskPack | 生成包，不调用同步模型 |
| `GET /api/synthesis/tasks` | Task Center 列表 | 任务状态/归档操作入口 |
| `POST /api/synthesis/tasks/{id}/rescan` | 扫描回包 | 仍须经过协议 Gate |

### 目录

- 后端：`backend/app/`
- 前端：`frontend/src/`
- TaskPack：`data/taskpack_golden/`、`backend/app/taskpack/`
- 外部 runs：`data/taskpack_golden/runs/<worker>/`
- Cognition：`backend/app/cognition/` 及其独立 catalog/collection 配置
- 报告/知识库索引：`backend/app/indexing/`、`backend/app/lexical/`、`backend/app/retrieval/`
- 相关协议：[TASKPACK_PROTOCOL_V1.md](D:/AI-Knowledge-Engine/docs/TASKPACK_PROTOCOL_V1.md)

### 术语

- **TaskPack**：固化任务、evidence、schema 和 Worker 交接约束的目录包；
- **Worker**：外部执行任务并写回结果的模型工具/窗口；
- **Cognition**：独立 source/catalog/collection 的 AI 知识整合体系；
- **FTS/lexical**：可解释的文本/字段检索路径；
- **dense/hybrid**：依赖向量索引的语义或混合检索；
- **evidence ref**：回到固定证据片段的引用；
- **epistemic state**：主张的认识层级；
- **proposal-first**：先候选/预览，再经用户确认和审计写入；
- **degraded**：依赖部分不可用但应用仍运行的明确降级状态，不是完整成功。
