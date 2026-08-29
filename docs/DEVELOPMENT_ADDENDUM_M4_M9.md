# AI 深度报告本地知识检索系统：M4–M9 后续开发实施计划

> 用途：交接给任意 Coding LLM / Coding Agent / 人类开发者继续实施  
> 当前起点：M3 Semantic Chunker 已完成并通过 Gate  
> 当前下一阶段：M4 Chinese Lexical / SQLite FTS5  
> 日期：2026-08-29

---

# 1. 当前项目状态

已完成：

```text
M0 环境与硬件验证
M1 项目骨架与 Storage
M2 Markdown Parser
M3 Semantic Chunker
```

M3 当前真实验收结果：

```text
M04 fixture:
816 lines
81 chunks

Chunk length:
Min   25
P25   167
P50   447
P75   772
P90   979
P95   1142
Max   1756
Mean  501.9
```

Content Types：

```text
causal_chain  13
prose         45
code           8
table          5
comparison     5
monitoring     1
reference      4
```

M3 Gate：

```text
Broken Table        0
Broken Formula      0
Cross-section       0
Invalid Line Range  0
Duplicate Chunk ID  0
Empty Chunk         0
```

测试：

```text
pytest: 45 passed
```

因此：

> **M3 判定通过，不回头继续人工调 Chunk 长度，立即进入 M4。**

---

# 2. 当前架构锁定

V1 继续采用：

```text
Source:
Markdown

Catalog / Metadata / FTS:
SQLite

Dense Vector:
Qdrant

Embedding:
Qwen3-Embedding-0.6B

Hybrid:
Dense + Terms + Trigram

Fusion:
Weighted RRF

Reranker:
Qwen3-Reranker-0.6B
```

前端：

```text
React + TypeScript + Vite
```

后端：

```text
Python 3.12 + FastAPI
```

---

# 3. 当前开发顺序

后续严格按照：

```text
M4 Chinese Lexical / SQLite FTS5
        ↓
M5 Qwen3 Dense Retrieval
        ↓
M6 Hybrid Retrieval / Weighted RRF
        ↓
M7 Qwen3 Reranker
        ↓
M8 Incremental Index
        ↓
M9 Golden Evaluation
        ↓
Retrieval Quality Gate
        ↓
M10 FastAPI
        ↓
M11 React Frontend
```

当前文档重点覆盖：

```text
M4 → M9
```

---

# 4. 核心原则

后续开发必须遵守：

1. 不重新解析原始 Markdown。
2. M4–M9 只消费当前 Parser / Chunker 的稳定输出。
3. 原始知识目录只读。
4. 不为了 UI 提前改 Retrieval 结构。
5. 不引入 LangChain / LlamaIndex 进入核心检索链。
6. 不使用 LLM 做 Query Planner。
7. 所有 Ranking 改动必须可解释。
8. 所有优化必须经过 Golden Set。
9. 不因为 ROCm/GPU 问题阻塞 Parser/FTS/Evaluation。
10. 在 Retrieval Quality Gate 之前，不投入大量工作做 React UI。

---

# 5. M4：Chinese Lexical / SQLite FTS5

优先级：

```text
P0
```

复杂度：

```text
L
```

目标：

> 建立可靠的中文专业词 + 精确技术 Identifier 召回能力。

---

# 6. M4 输入

输入必须来自：

```text
Chunk.raw_markdown
Chunk.plain_text
Chunk.heading_path
Chunk.document_id
Chunk.chunk_id
```

禁止：

```text
重新读取原始 Markdown
重新切 Chunk
```

---

# 7. M4 推荐结构

```text
Chunk.plain_text
      │
      ├───────────────┐
      │               │
      ▼               ▼
Terms Pipeline    Trigram Pipeline
      │               │
      ▼               ▼
FTS Terms         FTS Trigram
```

查询：

```text
User Query
    │
    ├─ Terms Query Parser
    │      ↓
    │   FTS Terms
    │
    └─ Exact / Trigram Query
           ↓
       FTS Trigram
```

---

# 8. M4 Terms Pipeline

推荐处理：

```text
Unicode NFKC
↓
技术 Identifier 保护
↓
中英文边界处理
↓
中文分词
↓
技术词典补充
↓
轻量 Stopword Filter
↓
lexical_text
↓
SQLite FTS5 unicode61
```

---

# 9. Technical Identifier Protector

必须确保以下类型整体保留：

```text
CoWoS-L
CoWoS-S
High-NA
EXE:5000
HBM4
HBM4E
MR-MUF
TC-NCF
N3E
N3B
A16
CFET
BSPDN
60mV/dec
429mm²
```

重点处理：

```text
-
:
/
+
.
_
```

禁止技术标识符被错误拆成：

```text
MR
MUF
```

或者被 FTS 解释为：

```text
column filter
operator
```

---

# 10. 中文分词

V1 可采用：

```text
jieba
+
config/tech_terms.txt
```

推荐：

```text
技术词词典
先注册进 jieba
```

而不是简单依赖默认词典。

允许：

```text
先进封装
→ 先进 / 封装
```

但不允许：

```text
CoWoS-L
→ CoWoS / L
```

---

# 11. Trigram Pipeline

Trigram 直接基于规范化文本建立。

用途：

```text
型号
精确技术词
混合字符
子串
数字+单位
```

例如：

```text
EXE:5000
CoWoS-L
429mm²
HBM4
```

---

# 12. M4 Query Parser

必须单独模块：

```text
app/lexical/query_parser.py
```

禁止：

```python
fts_match(user_query)
```

正确流程：

```text
User Query
↓
识别 Identifier
↓
识别中文词
↓
安全转义
↓
构造 FTS5 Expression
```

示例：

```text
CoWoS-L
→ "CoWoS-L"

EXE:5000
→ "EXE:5000"
```

---

# 13. M4 必须测试的字符

至少覆盖：

```text
-
:
/
+
.
_
```

示例：

```text
High-NA
EXE:5000
60mV/dec
A16+
N3.E
TC_NCF
```

---

# 14. M4 Retrieval Modes

至少实现：

```text
terms
trigram
lexical_combined
```

M4 阶段暂时不要接 Dense。

---

# 15. M4 Combined Lexical

初期可以用：

```text
RRF
```

融合：

```text
Terms Top-K
+
Trigram Top-K
```

不要直接混合原始 BM25 score。

---

# 16. M4 测试报告

完成后必须输出：

```text
lexical_text 示例
Terms FTS chunk count
Trigram FTS chunk count
chunks table count
```

必须验证：

```text
chunks
=
fts_terms
=
fts_trigram
```

除非存在明确的排除规则。

---

# 17. M4 Exact Query Test Set

至少：

```text
CoWoS-L
CoWoS-S
High-NA
EXE:5000
HBM4
HBM4E
MR-MUF
TC-NCF
N3E
N3B
A16
CFET
BSPDN
60mV/dec
429mm²
```

要求：

```text
Hit@5 接近 100%
```

精确技术词搜不到，M4 不通过。

---

# 18. M4 Chinese Query Test Set

至少：

```text
先进封装
铜互连
散热良率
混合键合
先进制程
资本开支
推理算力
电网瓶颈
半导体周期
AI 基础设施
```

要求：

```text
Top 5 至少出现正确章节
```

---

# 19. M4 不要只使用 M04

从 M4 开始，新增至少：

```text
3–5 篇代表性报告
```

类型建议：

```text
半导体          1
AI 模型/算法     1
AI 基础设施      1
宏观/投资        1
其他技术         1
```

目的：

```text
避免只围绕 M04 调参
```

---

# 20. M4 Gate

必须：

```text
Identifier Query No Syntax Error
Exact Hit@5 >= 0.95
Chinese Lexical 基本可用
FTS Count Consistency PASS
pytest PASS
```

并输出：

```text
M4_EVALUATION.md
```

---

# 21. M5：Qwen3 Dense Retrieval

优先级：

```text
P0
```

复杂度：

```text
M
```

目标：

> 建立语义检索能力。

---

# 22. M5 Embedding Model

锁定：

```text
Qwen/Qwen3-Embedding-0.6B
```

默认维度：

```text
1024
```

---

# 23. Query Instruction

查询必须使用 instruction。

推荐：

```text
Given a query for a private research knowledge base, retrieve the most relevant
passages from Chinese and English technical, semiconductor, AI, macroeconomic,
industry, and investment research reports. Preserve exact entities, model names,
technical terms, causal relationships, quantitative indicators, and evidence levels.
```

必须配置化。

---

# 24. Embedding Input

文档向量使用：

```text
Chunk.embedding_text
```

不要重新构造第二套模板。

---

# 25. M5 Qdrant

Collection：

```text
kb_chunks_v1
```

Vector：

```text
dense
1024
COSINE
```

Payload 至少：

```text
chunk_id
document_id
section_id
content_type
evidence_level
domain
completed_at
```

---

# 26. Qdrant Source of Truth

继续保持：

```text
SQLite
=
Canonical Catalog
```

```text
Qdrant
=
Rebuildable Dense Index
```

禁止只在 Qdrant 保存唯一正文。

---

# 27. M5 AMD Device Rules

当前硬件已知：

```text
RX 7900 XTX
+
iGPU
```

所有推理必须使用：

```text
get_inference_device()
```

禁止：

```python
.cuda()
device="cuda"
```

---

# 28. Device Selection

继续采用：

```text
force_device
>
preferred_gpu_name
>
最大显存
>
CPU fallback
```

配置：

```yaml
inference:
  preferred_device: auto
  preferred_gpu_name: "RX 7900 XTX"
  force_device: null
```

---

# 29. ROCm 锁定

当前继续保持：

```text
torch 2.9.1
ROCm 7.13.0
```

不要升级。

升级前必须重新执行：

```text
scripts/run_m0_smoke.ps1
```

---

# 30. GPU Worker Process

建议 M5 开始实现最小版本。

结构：

```text
Backend
  │
  ▼
Inference Worker
  │
  ▼
GPU
```

目标：

```text
GPU process crash
≠
Backend crash
```

如果当前 M5 实现成本过高，可：

```text
M5 先完成 Provider
M7 再完成 Worker Process
```

但必须保留任务。

---

# 31. M5 Dense Query Test

必须包含语义改写：

```text
为什么大型 AI GPU 对先进封装越来越依赖？
```

预期能命中：

```text
CoWoS / HBM / Packaging Compensation
```

另：

```text
为什么先进光刻反而可能降低大芯片经济性？
```

应命中：

```text
High-NA / field size / stitching
```

---

# 32. M5 Gate

必须：

```text
Qwen Embedding smoke PASS
RX 7900 XTX device PASS
CPU fallback PASS
Qdrant insert PASS
Qdrant search PASS
Semantic Query 基本命中
pytest PASS
```

输出：

```text
M5_DENSE_EVALUATION.md
```

---

# 33. M6：Hybrid Retrieval / Weighted RRF

优先级：

```text
P0
```

复杂度：

```text
M
```

目标：

> 第一次形成完整搜索引擎能力。

---

# 34. M6 Candidate Sources

三路：

```text
Dense
Terms
Trigram
```

建议：

```text
Dense Top 50
Terms Top 50
Trigram Top 30
```

---

# 35. M6 Fusion

使用：

```text
Weighted RRF
```

初始：

```text
k = 60
dense_weight = 1.0
terms_weight = 0.9
trigram_weight = 0.7
```

禁止直接：

```text
cosine * 0.7
+
bm25 * 0.3
```

---

# 36. Candidate Debug Object

每条候选必须记录：

```text
dense_rank
terms_rank
trigram_rank
rrf_score
```

用于 Debug。

---

# 37. Dedup

同一：

```text
chunk_id
```

只保留一条。

---

# 38. Section Parent Boost

如已实现 Section Dense：

只作为轻量 Prior。

禁止：

```text
Section miss
→ 子 Chunk 全过滤
```

---

# 39. M6 Search Modes

至少：

```text
dense
lexical
hybrid
```

方便对比。

---

# 40. M6 Test Query 类型

必须覆盖：

```text
Exact
Semantic
Causal
Comparison
Metric
Monitoring
Overview
```

---

# 41. M6 Gate

必须输出：

```text
Dense only
Lexical only
Hybrid
```

同一批 Query 的：

```text
Hit@5
MRR
```

原则：

> Hybrid 不得整体显著差于 Dense 和 Lexical。

---

# 42. M7：Qwen3 Reranker

优先级：

```text
P0
```

复杂度：

```text
M
```

模型：

```text
Qwen/Qwen3-Reranker-0.6B
```

---

# 43. Reranker Pipeline

```text
Hybrid Top 30
↓
Dedup
↓
Top 24
↓
Reranker
↓
Final Top 10
```

---

# 44. Reranker Input

建议：

```text
Query

Document:
{title}

Section:
{heading_path}

Evidence:
{evidence}

Content:
{plain_text}
```

---

# 45. Reranker Batch

Windows ROCm 初始：

```text
batch_size = 1
```

依次 benchmark：

```text
1
2
4
8
```

只保存稳定值。

---

# 46. GPU Worker Process

如果 M5 未完成进程隔离：

M7 必须优先完成。

因为 Reranker 是：

```text
交互式查询阶段
```

GPU crash 更容易影响 Backend。

---

# 47. M7 Gate

必须比较：

```text
Hybrid
vs
Hybrid + Reranker
```

要求：

```text
MRR 不下降
Hit@5 不明显下降
Top1 质量改善
```

如果 Reranker 降低质量：

```text
默认关闭
```

不要为了“架构完整”强行保留。

---

# 48. M8：Incremental Index

优先级：

```text
P0
```

复杂度：

```text
L
```

目标：

> 让知识库可以长期维护。

---

# 49. 文件状态

保存：

```text
path
size
mtime_ns
sha256
```

---

# 50. Fast Path

如果：

```text
size unchanged
+
mtime unchanged
```

允许：

```text
skip sha256
```

---

# 51. Change Pipeline

```text
File Changed
↓
Parse to staging
↓
Validate
↓
Chunk
↓
SQLite transaction
↓
Embedding
↓
Qdrant replace
↓
FTS sync
↓
Commit generation
```

---

# 52. 禁止先删除旧数据

错误流程：

```text
delete old
↓
parse
↓
parse failed
↓
document disappears
```

必须 staging。

---

# 53. 文件操作场景

M8 必须测试：

```text
Add
Modify
Rename
Delete
Crash
Restart
```

---

# 54. Watcher + Reconcile

必须：

```text
watchdog
+
periodic full manifest reconciliation
```

Watcher 不能作为唯一来源。

---

# 55. Tombstone

删除文件建议保留：

```text
deleted_at
last_path
last_sha256
```

---

# 56. M8 Gate

必须：

```text
Add PASS
Modify PASS
Rename PASS
Delete PASS
Crash Recovery PASS
No Orphan Qdrant Point
No Orphan FTS Row
```

---

# 57. M9：Golden Evaluation

优先级：

```text
P0
```

复杂度：

```text
L
```

这是整个项目最重要的质量 Gate。

---

# 58. Golden Dataset

文件：

```text
tests/retrieval/golden_queries.jsonl
```

每条：

```json
{
  "id": "M04_Q001",
  "query": "High-NA 为什么对大型 AI 芯片不友好？",
  "expected_document_ids": ["M04"],
  "expected_section_ids": ["M04:ch2-2"],
  "required_terms": ["429", "Mask Stitching"],
  "tags": ["causal", "semiconductor"]
}
```

---

# 59. Query 类型

至少：

```text
Exact
Semantic
Causal
Comparison
Metric
Monitoring
Overview
Reference
Cross-document
```

---

# 60. Golden Set 数量

第一版：

```text
30–50 queries
```

不要少于 30。

---

# 61. 多文档覆盖

至少来自：

```text
5 篇以上不同报告
```

不要只基于 M04。

---

# 62. Metrics

至少：

```text
Hit@1
Hit@3
Hit@5
Recall@5
Recall@10
MRR@10
NDCG@10
```

---

# 63. Ablation

必须比较：

```text
Terms only
Trigram only
Lexical combined
Dense only
Dense + Terms
Dense + Trigram
3-way Hybrid
Hybrid + Reranker
```

---

# 64. Chunker 回归判断

当前 Chunk P50 较短：

```text
P50 = 447
```

不要现在修改。

只在 M9 中：

如果数据显示：

```text
Recall 明显受影响
```

再 A/B：

```text
Current Chunker
vs
更强相邻段合并
```

没有数据前不要重构 M3。

---

# 65. 表前引导句问题

当前已知：

```text
部分短引导句
+
后续 Table
```

被分成两个 Chunk。

暂不修复。

M9 中加入相关 Query。

如果：

```text
Table 命中下降
```

再增加：

```text
table-leading-context
```

规则。

---

# 66. Retrieval Quality Gate

建议初始目标：

```text
Hit@5 >= 0.90
MRR@10 >= 0.75
NDCG@10 >= 0.80
```

这些不是永久标准。

但必须有定量 Gate。

---

# 67. 未达标时禁止做什么

如果 M9 未达标：

禁止：

```text
用 LLM Answer Generation 掩盖
直接开始漂亮前端
增加复杂 Agent
```

应依次检查：

```text
Chunk
Lexical
Embedding Instruction
RRF
Metadata Filter
Reranker
```

---

# 68. Debug Search Mode

在 M6 前后必须具备：

```text
debug=true
```

返回：

```text
Dense Top-K
Terms Top-K
Trigram Top-K
RRF
Reranker
Filter
Timing
```

---

# 69. Performance Trace

Search 必须记录：

```text
embed_ms
dense_ms
terms_ms
trigram_ms
fusion_ms
rerank_ms
total_ms
```

---

# 70. 后续禁止事项

后续 LLM 不得擅自：

```text
SQLite → Postgres
Qdrant → Pinecone
Qwen → Cloud API
React → Streamlit
pip → poetry
pip → conda
Chunker 重写
Parser 重写
```

如确需改变：

必须先写 ADR。

---

# 71. 每个 Milestone 交付格式

每完成一个阶段：

```text
1. Code
2. Tests
3. Commands Run
4. Test Results
5. Evaluation Result
6. Known Issues
7. ADR Changes
8. IMPLEMENTATION_STATUS.md
9. Git Commit
```

---

# 72. Git Checkpoint

建议：

```text
M4 complete
M5 complete
M6 complete
M7 complete
M8 complete
M9 complete
```

每个阶段一个独立 commit。

---

# 73. 下一窗口当前立即执行任务

直接开始：

```text
M4 Chinese Lexical / SQLite FTS5
```

要求：

```text
1. 实现 Technical Identifier Protector
2. 实现 Unicode Normalizer
3. 实现 jieba + tech_terms
4. 生成 lexical_text
5. 建立 Terms FTS
6. 建立 Trigram FTS
7. 实现 Safe Query Parser
8. 实现 Terms Search
9. 实现 Trigram Search
10. 实现 Lexical Combined
11. 增加 Exact Query Tests
12. 增加 Chinese Query Tests
13. 引入 3–5 篇额外真实报告 fixture
14. 输出 M4_EVALUATION.md
15. 更新 IMPLEMENTATION_STATUS.md
16. Git checkpoint
```

---

# 74. M4 完成后必须汇报

必须输出：

```text
Chunks Count
FTS Terms Count
FTS Trigram Count

Exact Query Hit@5
Chinese Query Hit@5

Terms Query Latency P50/P95
Trigram Query Latency P50/P95
Combined Latency P50/P95

15 个技术 Identifier 测试结果
特殊字符测试结果

pytest passed count
```

---

# 75. M4 通过条件

最低：

```text
No FTS syntax errors
No index inconsistency
Exact Hit@5 >= 0.95
Chinese Query 基本正确
All tests PASS
```

通过后：

```text
进入 M5
```

---

# 76. M5–M9 总目标

最终在 M9 结束时，系统应具备：

```text
关键词找得到
型号找得到
中文专业词找得到
语义改写找得到
因果问题找得到
比较问题找得到
监测指标找得到
跨文档结果可排序
```

并且：

```text
每一个结果都能解释为什么排在这里
```

---

# 77. 最终交接指令

给接手 LLM：

> 当前 M0–M3 已完成，不要重做。  
> 从 M4 开始，严格按本计划执行。  
> 不要一次性实现 M4–M9。  
> 每完成一个 Milestone，先测试、评估、更新状态并 Git commit，再进入下一阶段。  
> 当前立即执行 M4 Chinese Lexical / SQLite FTS5。  
> 如果不存在真正 blocker，不要停下来询问用户。  
> Retrieval Quality Gate 通过以前，不投入大量时间开发 React UI。  
> 任何重大架构变更必须先写 ADR，并说明为什么现有方案无法满足需求。

---

# 78. 当前总体策略

整个项目当前最重要的事情不是“完成更多代码”，而是：

```text
M4
让 Exact / Chinese Recall 稳定
        ↓
M5
让 Semantic Recall 稳定
        ↓
M6
让 Hybrid Ranking 稳定
        ↓
M7
验证 Reranker 是否真正提高质量
        ↓
M8
保证长期可维护
        ↓
M9
用 Golden Set 证明搜索质量
```

只有完成这一闭环：

```text
Retrieval Quality Gate
```

才进入：

```text
FastAPI Productization
+
React Frontend
+
后续 MCP / RAG
```

**最终判断标准：真实查询是否能稳定找到正确知识，而不是代码是否已经“跑起来”。**
