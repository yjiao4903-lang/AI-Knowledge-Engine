"""L1：Evidence-grounded Synthesis（主计划 L1A）。

synthesis/ 是 KE 内新增的生成式子系统，只提供结构化研究草稿生成，
不持有任何 Cognition 写权限（L1A 硬约束：只 read evidence → generate draft →
return draft）。子模块：

- schemas.py    SynthesisDraft Schema V1 + epistemic_state 枚举
- prompt.py     Context Envelope + SYSTEM POLICY + 输出 Schema 组装
- grounding.py  证据解析（Evidence ref -> 正文）+ 引用合法性
- validator.py  Draft 校验与 L1A 指标计算
- provider.py   SynthesisProvider 抽象（Ollama / Mock）
- service.py    编排：ground -> prompt -> provider -> validate
"""

from __future__ import annotations