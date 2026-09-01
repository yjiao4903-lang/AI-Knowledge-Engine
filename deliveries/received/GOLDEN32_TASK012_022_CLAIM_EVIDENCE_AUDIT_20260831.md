# Golden32 候选集 task_012–task_022 claim-evidence 审计

日期：2026-08-31。范围为候选目录 `GOLDEN32_FINAL_20260831_010542/candidate/task_012..task_022`，固定证据使用各任务同目录 `evidence.jsonl`；未修改结果、source 或 runs。

## 总结

- 覆盖 11/11 个任务、133/133 个对象：116 claims、17 tensions。
- 逐对象审计分类：`pass` 69、`partial` 35、`uncertain` 29、`fail` 0。
- 直接 pass 率：69/133 = 51.9%。若将 partial/uncertain 误合并为 pass，会掩盖推断、预测和 tension 的证据边界，因此不采用宽松通过率。
- 固定 evidence 引用可定位：无效引用 0；Critical Contradiction：0（未发现证据明确反驳对应主张）。
- 任务覆盖：task_012 14、013 13、014 13、015 14、016 13、017 13、018 14、019 7、020 15、021 11、022 6 个对象。

逐对象审计明细见同目录的 [task012-022_claim_evidence_audit.tsv](D:/AI-Knowledge-Engine/deliveries/received/GOLDEN32_FINAL_20260831_010542/task012-022_claim_evidence_audit.tsv)。该表逐行包含 task、对象类型/ID、原始 epistemic state、entailment 判定、evidence refs、时间/预测/量化/因果标记和短理由。

## 高风险复核

- `task_012/claim_007`：2026/2027E 与 HBM4E 规格已标 uncertain，时间和前瞻口径没有当作事实。
- `task_013/claim_005`：性能参数引用可定位，但含“L1 因果证实”标签；该标签本身不是独立因果证据，保留为需人工注意的 partial 风险。
- `task_013/claim_006`：3.2T 时代“不可替代”已标 uncertain，符合未来预测边界。
- `task_013/claim_008`：产业化瓶颈及“导致光散射”涉及机制因果，固定 evidence 能支持材料机制，但产业化总括仍需谨慎，列 partial 风险。
- `task_014/claim_003-005`：未来目标、预测性后果和“不可逆漂移”均降为 inference，市场份额估算为 uncertain；其 tensions 亦为 uncertain。
- `task_015/claim_003/006-008`：foundry/CoWoS/HBM 份额及 2026E 产能、供应预测均为 uncertain，并保留来源和预测口径。
- `task_017/claim_005/012`：由位宽到封装价值的关系明确标 inference，没有把可能机制标为事实因果。
- `task_018/claim_010-012`、`task_020/claim_007/009`：2030 年、TDP、渗透率、电网余量等前瞻/统计口径均标 uncertain；`task_020/tension_001` 保留来源时间口径张力。
- `task_019/claim_004`：PFAS 约束到供应链替代的关系标 inference，保留“可能迫使”和不确定性。
- `task_022/claim_005`：过度训练是 TCO 条件下的演化方向，已标 inference，并明确依赖 Q≫D、高并发等前提；但该 task 的 tension 同样只能作为 uncertain，不能宣称直接事实。

## 需要重做或人工升级复核的对象

本批未发现应判 `fail` 的无证据或反证对象；但以下对象不应按简单 supported 事实直接导入，建议在正式导入前人工复核：

1. `task_013/claim_005`、`task_013/claim_008`：分别涉及 L1 因果标签和产业化瓶颈机制；应确认 evidence 是否直接支持完整因果链，必要时拆为物理事实 + inference。
2. `task_012/claim_001`、`task_017/claim_001`：HBM4 位宽/带宽产业共识口径，引用支持规格陈述，但应保留 L3/产业共识限定，不能升级成已验证出货事实。
3. `task_018/claim_010-012`、`task_020/claim_007/009`：前瞻预测已正确标 uncertain，无需重写状态，但导入审批时必须保留预测来源、年份和限定词。
4. 所有 17 个 tensions：当前大多为 uncertain，语义上合理；不可将 tension 的“存在”误读为两端事实均已被直接证实。

## 审批建议

本 11-task 子集的引用定位和认识层级表现可进入人工审批，但不能仅凭本表宣称全量 Citation Entailment >=90%。建议主负责人使用 TSV 做逐行复核，重点覆盖上列高风险对象和全部 tensions；在确认 partial/uncertain 的证据蕴含后，再决定是否纳入正式导入候选。不得自动写入 Cognition/Proposal。
