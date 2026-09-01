# R2.1 task_018 修正启动提示词

这是 R2.1 的单任务修正包。请从零重新完成包内 `task_018`，绝对不要读取、参考或复用 R1/R2 的任何历史 result、摘要、报告或外部文件。

只允许读取当前 `task_018/` 内的 `task.yaml`、`AGENT_INSTRUCTION.md`、`evidence.jsonl`、`output_schema.json`、`README.md`、`manifest.json`。只能依据本任务固定 evidence 作答，不得联网、读取包外资料、安装依赖或修改知识库/Cognition/Proposal。

核心修正要求：

1. 将“GPU 功耗上升”和“风冷在 40–50 kW/机架失效”等证据直接支持的事实拆开表达；证据未直接证明的“功耗上升导致风冷失效”“因此必然转向液冷”等强因果，不得标为 `supported`。如保留因果解释，必须明确标为 `inference` 或 `hypothesis`，并在 rationale 中说明它是综合推断及证据边界。
2. Rubin 约 1,800W+、液冷渗透率预测、2030 用电、2027 电网负荷等未来/估算/预测/市场比例口径必须保留原有限定词，并标为 `uncertain`、`inference` 或 `hypothesis`，不得标为 `supported`。
3. 只引用本任务 `evidence.jsonl` 中逐字存在的 chunk_id；不扩大证据含义，不把相关性或时间顺序写成直接因果。证据不足时写入 uncertainties、open_questions、additional_evidence_needed。
4. 完整生成 `task_018/result/result.json` 和 `task_018/result/run_meta.json`；自检 schema、引用成员关系和认识状态后，最后创建 `task_018/result/DONE`。失败则写 `error.json` + `FAILED`，不要创建 DONE。不要写 CoT。

完成后，将结果复制到包根：
`RETURN/codex-external-smoke-r2-1/task_018/result/`

保持原始 `task_018/` 输入不变，不要把结果写回原始目录，不要复用任何历史 result。最后回复实际生成文件、模型和完成状态。
