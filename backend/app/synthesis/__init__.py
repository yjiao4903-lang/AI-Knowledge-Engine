"""L1：Evidence-grounded Synthesis（TaskPack V1 外部模型工作流，V3.0 方案 §32）。

synthesis/ 保留证据定位与校验所需的共享模块：

- schemas.py    SynthesisDraft Schema V1 + epistemic_state 枚举
- grounding.py  证据解析（Evidence ref -> 正文）+ 引用合法性
- validator.py  Draft 校验与 L1A 指标计算

原本地 LLM 路线（provider/prompt/service）已按 V3.0 方案从生产移除
（git history 可回溯）；生成改由 TaskPack 目录 + 外部 Worker 完成，
TaskPack 实现位于 app/taskpack/。
"""

from __future__ import annotations