# AI 深度报告本地知识检索系统：阶段开发评估与后续实施补充说明

> 用途：在 M0–M2 已完成的基础上，指导后续 LLM / Coding Agent 继续开发  
> 当前阶段：M3 Semantic Chunker  
> 依据：当前 `IMPLEMENTATION_STATUS.md` 与既定项目开发规格  
> 日期：2026-08-29

---

# 1. 当前项目状态判断

当前项目整体进展健康，可以继续进入：

```text
M3 Semantic Chunker
```

不建议回头重构 M0–M2。

目前已完成：

```text
M0 环境与硬件验证
M1 项目骨架与 Storage
M2 Markdown Parser
```

M2 已经不是“代码能运行”的表面完成，而是具备真实报告 fixture、结构统计和自动化测试。

当前 M04 fixture 验收结果：

```text
Document Lines: 816
Sections: 64
H1: 8
H2: 23
H3: 33
Parser Blocks: 130
```

Block 类型：

```text
prose          103
ascii_diagram   12
code             8
table            6
mermaid          1
```

并已经正确识别：

```text
metadata
summary
toc
monitoring
reference
audit
```

当前测试：

```text
pytest: 31 passed
```

因此，M2 已经能够作为后续 Chunker 的稳定输入层。

---

# 2. M3 的任务边界

M3 的职责应严格限制为：

```text
M2 MarkdownParser 输出
        ↓
Section + Block
        ↓
Semantic Chunker
        ↓
Chunk Objects
```

## 禁止事项

M3 不得：

```text
再次重新解析原始 Markdown
再次使用正则从原文件猜标题
修改 M2 Heading Tree
重新生成 Section ID
修改原始知识文件
把表格粗暴切断
把公式与解释拆开
跨 Section 合并 Chunk
```

原则：

> M3 应消费 M2 已经产生的结构化 AST / Section / Block，而不是重新建立第二套 Markdown 解析逻辑。

---

# 3. M3 核心 Chunking 原则

优先级必须为：

```text
1. 语义完整性
2. Section 边界
3. 特殊块完整性
4. Chunk 长度
```

而不是：

```text
固定长度优先
```

---

# 4. 推荐 Chunk 长度参数

初始 Baseline：

```text
target_chars     = 900
soft_min_chars   = 350
soft_max_chars   = 1400
hard_max_chars   = 2200
overlap_chars    ≈ 100
```

这些参数只是初始值。

后续必须通过 Golden Query Set 调整，而不是长期写死。

---

# 5. Hard Max 的例外对象

以下对象不能为了满足 `hard_max_chars` 强制拆分：

```text
Markdown Table
Formula + Explanation
Mermaid Diagram
ASCII Causal Diagram
Monitoring Table
Decision Tree
Comparison Table
完整列表结构
```

如果特殊对象本身超过限制：

```text
生成单独 Chunk
↓
允许 oversized
↓
设置 oversized = true
```

宁可产生一个超长 Chunk，也不要破坏知识结构。

---

# 6. 每个 Chunk 建议至少保存三种文本

M3 不应只生成一份字符串。

每个 Chunk 至少保存：

```text
raw_markdown
plain_text
embedding_text
```

## 6.1 raw_markdown

用途：

```text
原文展示
Document Viewer
引用
定位
调试
```

要求最大程度保持原始 Markdown。

## 6.2 plain_text

用途：

```text
SQLite FTS5
Snippet
Reranker
关键词提取
调试
```

处理：

```text
Markdown 标记适度清理
保留技术词
保留数字
保留公式文本
保留关键单位
```

不要把以下技术实体清洗掉：

```text
HBM4
CoWoS-L
EXE:5000
N3E
60mV/dec
```

## 6.3 embedding_text

禁止直接：

```text
embedding_text = plain_text
```

建议构造：

```text
Document: {document_title}
Domain: {domain}
Section:
{heading_path}
Content Type:
{content_type}
Evidence:
L{evidence_level}

{plain_text}
```

这样在未来 7000+ Markdown 跨文档检索时，Chunk 会拥有更强的上下文可辨识度。

---

# 7. Chunk ID 必须稳定

Chunk ID 不应该依赖随机 UUID。

推荐：

```text
document_id
+
section_id
+
ordinal
```

例如：

```text
M04:ch3-2:0004
```

如果 Chunk 算法变化：

```text
chunker_version
```

负责判断是否需要重新索引。

---

# 8. Line Range 必须继承

每个 Chunk 必须保存：

```text
start_line
end_line
```

要求：

```text
1-based
start_line <= end_line
必须处于原文范围内
```

未来 Search Result 点击“查看原文”需要依赖这一信息。

---

# 9. Content Type 继承与细化

当前 Parser 已经识别：

```text
prose
table
code
mermaid
formula
ascii_diagram
```

Chunker 可以进一步映射为：

```text
prose
summary
claim
causal_chain
table
formula
comparison
decision_tree
monitoring
reference
audit
code
```

但不要为了分类调用大型 LLM。

V1 优先采用：

```text
Section Type
+
Block Type
+
规则判断
```

---

# 10. Evidence Level 处理

现有 Parser 已经支持：

```text
[L1] ~ [L5]
```

Chunk 应继承：

```text
evidence_level
evidence_levels
```

如果一个 Chunk 存在 L1/L2/L3，建议：

```text
evidence_level = 1
evidence_levels = [1,2,3]
```

保留完整数组。

---

# 11. M3 验收时必须输出统计

完成 M3 后，不接受仅汇报：

```text
pytest passed
```

必须同时输出真实报告统计：

```text
M04
Sections: 64
Parser Blocks: 130
Generated Chunks: N
```

Chunk Length Distribution：

```text
Min
P25
P50
P75
P90
P95
Max
Mean
```

同时统计：

```text
Oversized chunks
Cross-section chunks
Invalid line ranges
Duplicate chunk IDs
Empty chunks
```

---

# 12. Content Type 统计

至少输出以下类型数量：

```text
prose
summary
claim
causal_chain
table
formula
comparison
decision_tree
monitoring
reference
audit
code
```

这样可以及时发现所有内容都被错误识别成 prose 等问题。

---

# 13. M3 人工抽样要求

自动测试之外，至少人工抽查：

```text
10 个普通 prose
5 个 table
3 个 formula
3 个 ASCII / causal diagram
3 个 monitoring / reference / audit
```

检查：

```text
语义是否完整
Heading Path 是否正确
Evidence 是否正确
Line Range 是否正确
是否发生断表
是否发生断公式
是否跨 Section
```

---

# 14. M3 必须达到的硬性验收条件

建议：

```text
Broken Table = 0
Broken Formula = 0
Cross-section Chunk = 0
Invalid Line Range = 0
Duplicate Chunk ID = 0
Empty Chunk = 0
```

如果这些项目存在问题：

```text
M3 不通过
```

不得进入 M4。

---

# 15. 当前 GPU 已知风险

当前环境已经确认：

```text
AMD Radeon RX 7900 XTX
+
AMD 核显
```

HIP 会同时枚举多个 GPU。

当前已发现：

```text
iGPU 被 HIP 枚举
↓
错误 Device 被选中
↓
Kernel Launch
↓
0xC0000005
↓
Python 进程级崩溃
```

现阶段已经通过：

```text
device.py
↓
按显存大小选择 GPU
↓
RX 7900 XTX
```

进行规避。

---

# 16. GPU 使用规则必须锁定

所有后续推理代码必须通过 `device.py` 获取 device。

禁止：

```python
model.cuda()
tensor.cuda()
device = "cuda"
```

应使用统一设备选择函数，例如：

```python
device = get_inference_device()
```

返回类似：

```text
cuda:1
```

或未来其他正确设备。

---

# 17. 增加显式 GPU 配置

在 M5 Dense Retrieval 前，建议增加：

```yaml
inference:
  preferred_device: auto
  preferred_gpu_name: "RX 7900 XTX"
  force_device: null
```

允许未来人工指定：

```yaml
force_device: "cuda:1"
```

优先级建议：

```text
force_device
>
preferred_gpu_name
>
最大显存
>
CPU fallback
```

---

# 18. ROCm 版本锁定

当前已经确认 Windows ROCm 的特定新版存在 Kernel Launch 回归。

因此目前锁定：

```text
torch 2.9.1
+
ROCm 7.13.0
```

升级 ROCm / PyTorch 前必须执行：

```text
scripts/run_m0_smoke.ps1
```

不得因为“有新版本”直接升级。

所有 ROCm/PyTorch 升级都必须经过：

```text
Smoke Test
+
Embedding Test
+
Reranker Test
+
Golden Retrieval Test
```

通过后才允许更新锁定版本。

---

# 19. GPU Worker 进程隔离建议

这是后续 M5/M7 前值得增加的架构保护。

Windows HIP 的：

```text
0xC0000005 Access Violation
```

属于进程级崩溃，通常无法通过 Python `try/except` 捕获。

因此最终建议：

```text
FastAPI
   │
   ▼
Inference Manager
   │
   ▼
GPU Worker Process
   │
   ▼
RX 7900 XTX
```

如果 GPU Worker 崩溃：

```text
Backend 仍然存活
↓
Worker restart
↓
必要时 CPU fallback
```

该功能不要求 M3 实现，建议在 M5 Dense Retrieval 或 M7 Reranker 阶段加入。

---

# 20. 当前 FTS5 已知风险

已经确认技术 Identifier：

```text
CoWoS-L
EXE:5000
```

直接输入 SQLite FTS5 时可能被解释成：

```text
FTS operator
column filter
```

导致错误或错误检索。

---

# 21. M4 必须实现统一 Query Parser

禁止调用层自己决定什么时候加双引号。

所有 Lexical Query 必须进入：

```text
User Query
↓
Lexical Query Parser
↓
Normalized Tokens
↓
Safe FTS5 Expression
```

例如：

```text
CoWoS-L
→ "CoWoS-L"

EXE:5000
→ "EXE:5000"
```

---

# 22. M4 技术词测试集

至少测试：

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

同时测试以下字符：

```text
-
:
/
+
.
_
```

---

# 23. 不要修改 SQLite 当前架构决定

当前已经决定：

```text
SQLite FTS
=
独立 Virtual Table
```

而不是：

```text
external-content FTS
```

由 `ChunkRepository` 负责与：

```text
chunks table
FTS table
```

在同一个 transaction 中同步。

当前没有必要改回 External Content。

---

# 24. 当前 Python / Storage 决策继续保持

目前已经锁定：

```text
pip
+
pyproject.toml
+
requirements-lock.txt
```

不需要重新切换：

```text
Poetry
uv
Conda
```

Torch 不放进普通 `pyproject dependencies` 是合理的，因为 AMD Windows ROCm 需要单独来源安装。

---

# 25. CPU 型号信息应避免人工写死

之前环境扫描与状态文件对 CPU 型号的描述存在轻微不一致。

这不影响实际开发。

但今后：

```text
diagnostic.json
runtime_profile.json
```

应直接调用系统 API 获取：

```text
CPU
GPU
Driver
RAM
ROCm
Torch
```

不要人工填写，避免环境信息随文档更新逐渐漂移。

---

# 26. 当前不需要修改完整开发规格书

现有主开发规格仍然有效。

不需要重新生成一套完整架构。

当前只需要把本文件作为：

```text
Implementation Addendum
```

加入项目：

```text
docs/
├─ ARCHITECTURE.md
├─ IMPLEMENTATION_STATUS.md
└─ DEVELOPMENT_ADDENDUM_M3_PLUS.md
```

---

# 27. 后续正确开发顺序

当前继续：

```text
M3 Semantic Chunker
        ↓
M4 Chinese Lexical / SQLite FTS5
        ↓
M5 Qwen3 Dense Retrieval
        ↓
M6 Hybrid RRF
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

---

# 28. 当前阶段最重要的三个模块

从整个系统最终质量看，后续最关键的模块并不是 Web UI。

优先级最高的是：

```text
M3 Semantic Chunker
M4 Chinese Lexical Retrieval
M9 Evaluation Harness
```

## M3

决定知识被怎样拆。

错误的 Chunk：

```text
Embedding 再强也无法完全修复
```

## M4

决定型号、公司、芯片节点、工艺术语、数字、专业词能否被可靠召回。

## M9

决定开发者是否真正知道：

```text
改动让检索变好了
还是变差了
```

没有 Evaluation，就只能凭感觉调 Retrieval。

---

# 29. 当前暂时不要开发前端

即使 FastAPI、React、Node、npm 都已经准备好，也暂时不要投入大量时间。

必须先完成：

```text
Dense
+
Lexical
+
Hybrid
+
Reranker
+
Golden Evaluation
```

并通过：

```text
Retrieval Quality Gate
```

之后才进入 UI。

---

# 30. 给下一开发窗口的直接任务

可以直接下达：

```text
继续执行 M3 Semantic Chunker。

请严格消费 M2 MarkdownParser 的 Section + Block 输出，
禁止重新解析原始 Markdown。

完成以下内容：

1. Chunk 数据模型补齐；
2. Semantic Chunking Rule Engine；
3. raw_markdown；
4. plain_text；
5. embedding_text；
6. stable chunk_id；
7. content_hash；
8. line range；
9. evidence inheritance；
10. special block preservation；
11. oversized handling；
12. Chunk statistics；
13. M04 fixture validation；
14. Unit Tests；
15. IMPLEMENTATION_STATUS.md 更新；
16. Git checkpoint。

完成后必须汇报：

- Generated Chunk Count
- Chunk length distribution
- Content Type distribution
- Oversized count
- Broken Table count
- Broken Formula count
- Cross-section count
- Invalid line ranges
- Duplicate chunk IDs
- pytest result
- 人工抽样结果

若不存在真正 blocker，不要停下来询问用户。
```

---

# 31. M3 完成后的 Gate

只有满足：

```text
Broken Table = 0
Broken Formula = 0
Cross-section Chunk = 0
Invalid Line Range = 0
Duplicate Chunk ID = 0
Empty Chunk = 0
Tests PASS
```

才进入：

```text
M4 Chinese Lexical / FTS5
```

---

# 32. 当前总体评价

目前项目没有显示出需要返工的结构性问题。

已有成果：

```text
环境可用
Storage 已建立
Markdown Parser 已通过真实报告验证
SQLite FTS5 可用
AMD GPU 风险已经提前暴露并有规避策略
ROCm 版本已经锁定
测试体系已经建立
```

因此当前最合理的策略是：

> **保持架构稳定，继续按照 Milestone 推进，不重新设计，不提前开发 UI。**

下一阶段的工作重点应集中在：

```text
Chunk Quality
↓
Lexical Recall
↓
Dense Recall
↓
Hybrid Ranking
↓
Evaluation
```

最终系统是否好用，由真实搜索结果决定，而不是由代码量或前端完成度决定。
