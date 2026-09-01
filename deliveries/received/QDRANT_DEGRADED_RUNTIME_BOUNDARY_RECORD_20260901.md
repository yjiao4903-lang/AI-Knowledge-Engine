# Qdrant 降级运行边界记录

日期：2026-09-01  
状态：**COMPLETED（降级边界、模拟失效测试及真实运行后验均已完成）**

## 边界结论

Qdrant 仅负责向量检索与向量索引能力，不是外部 TaskPack 归档读取的功能前提。Qdrant 不可用时，TaskPack 已归档结果的文件读取、结构化解析和只读摘要/API 能力可以继续按各自实现边界运行；这不等于向量检索成功。

## Qdrant 不可用时允许的只读能力

在补丁和验证确认前，仅可将以下能力作为“允许尝试的只读路径”，不能预先宣称运行通过：

- 读取已归档 TaskPack run 的目录、任务元数据和结果文件；
- 解析已存在的 `result.json`、`run_meta.json`、`DONE` 及结构化摘要；
- 通过不依赖 Qdrant 的只读 API 返回 run/任务列表、任务详情或摘要（需以实际 API 验证为准）。

## 必须降级并明确失败的能力

Qdrant 不可用时，以下能力必须明确返回降级/失败状态，不得伪装成成功：

- 向量相似度检索、语义检索和依赖 Qdrant 的检索过滤；
- 创建、更新或查询 Qdrant 向量索引；
- 任何声称“已完成向量召回”“检索结果完整”或“索引已同步”的响应。

如果产品接口仍返回可用的文件摘要或任务详情，应明确标注其为归档文件读取结果，而非 Qdrant 检索结果；检索失败原因和降级状态应可被调用方识别。

## 已实现与测试结果

- Qdrant 初始化失败不阻止应用启动。
- runs API 在 Qdrant 不可用时仍可读取。
- dense 检索、hybrid 检索及索引写操作在降级状态下明确返回 `503`。
- 模拟 Qdrant 失效测试：`2 passed`。
- 真实运行后验：8765 新进程已加载补丁。
- `GET /api/health`：HTTP `200`；`status=degraded`、`sqlite=ok`、`qdrant=error`。
- 健康状态中的检索能力：`retrieval.qdrant_available=false`、`dense_search=unavailable`。
- `GET /api/taskpack/runs`：HTTP `200`，包含 Golden32，`task_count=32`。
- Golden32 run 详情：HTTP `200`，返回 32 项任务。
- 5173 代理：HTTP `200`。
- 真实后验确认 Qdrant 降级状态可见，且检索不可用未被伪装为成功。

## 数据与知识边界

本记录不涉及 Cognition/Proposal 写入，不授权任何自动导入、知识晋升或正式知识变更。Qdrant 降级不得触发外部 TaskPack 自动写入 Cognition/Proposal，也不得改变 `supported`、`partial/inference`、`uncertain` 等既有认识状态。

## 待补全运行验证

- [x] 应用降级边界补丁并完成模拟失效测试；
- [x] 验证 runs API 在 Qdrant 初始化失败时仍可读取；
- [x] 验证 dense/hybrid 检索和索引写操作明确返回 `503`；
- [x] 真实运行服务重启结果：8765 新进程已加载补丁；
- [x] 真实运行服务 health 结果：HTTP 200，status=degraded，sqlite 正常、Qdrant 报错；
- [x] 真实运行中确认 runs API、run 详情和 5173 代理可用；
- [x] 真实运行中确认 dense/hybrid 检索不可用状态可识别，未伪装为成功。

当前结论：降级边界已实现，模拟失效测试通过，真实运行后验完成；Qdrant 当前为明确可见的 degraded 状态，归档读取/API 可用不等于向量检索可用。未修改业务数据。
