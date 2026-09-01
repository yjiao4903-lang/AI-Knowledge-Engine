# TaskPack Evaluation Report（external-codex-taskpack-smoke-r2-20260830）

日期：生成于运行时刻 ｜ 模型：外部 Worker（本报告只做无模型校验）
Golden 输入：`data/taskpack_golden/` ｜ Worker 结果：`data/taskpack_golden/runs/external-codex-taskpack-smoke-r2-20260830/`
N = 5 个任务包

## 汇总（§74 自动 Gate）

| Gate | 要求 | 本 Run |
|---|---|---|
| TaskPack Manifest 100% valid | =N | 4/5 |
| Result Schema 100% valid | =N | 4/5 |
| Citation Invalid Tasks | =0 | 0 |
| Citation Coverage >=95% | >=N | 4/5 |
| Unsupported Claim Rate <=5% | <=N | 4/5 |
| 全通过 | — | 4/5 |

## 逐任务指标

| task_id | manifest | schema | citation_invalid | cov | unsup | stale | 通过 | 失败 Gate |
|---|---|---|---|---|---|---|---|---|

| RETURN | ✗ | ✗ | 0 | — | — | — | FAIL | 缺 result/result.json |
| 20260830_180537_hbm4-hbm | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |
| 20260830_180537_task | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |
| 20260830_180537_ai | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |
| 20260830_180538_hbm | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |

## 人工 Entailment 审核表（§56）

需要人工标注：每行 evidence 是否 entail 该 claim（rides / supports / contradicts / unknown）与备注。

| task_id | claim_id | epistemic | claim_text | evidence_chunk_id | entailment | note |
|---|---|---|---|---|---|---|

| task_001 | claim_001 | supported | 前代 HBM 包括 HBM2E（2020 年商用）、HBM3（2023 年商用）与 HBM3e（2024 年商用）的接口位宽（Bus Width）均固定在 1024-bit。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_001 | supported | 前代 HBM 包括 HBM2E（2020 年商用）、HBM3（2023 年商用）与 HBM3e（2024 年商用）的接口位宽（Bus Width）均固定在 1024-bit。 | M05:ch2-2:o2:0026 |  |  |
| task_001 | claim_002 | supported | 前代 HBM 在 1024-bit 位宽下引脚速率持续提升，HBM2E 为 3.6 Gbps，HBM3 为 6.4 Gbps，HBM3e 进一步提升至 9.6 Gbps。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_003 | supported | HBM4 相比前代实现了接口位宽翻倍，从 HBM3/3e 的 1024-bit 跃升至 2048-bit。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_003 | supported | HBM4 相比前代实现了接口位宽翻倍，从 HBM3/3e 的 1024-bit 跃升至 2048-bit。 | M05:ch2-2:o2:0026 |  |  |
| task_001 | claim_006 | inference | 在位宽翻倍（2048-bit）与引脚速率提升（11.7~13.0 Gbps）的协同演进下，HBM4 单栈峰值带宽在报告中提升至 2.0~3.3 TB/s（M05 记述单堆栈带宽突破 2.0~3.0 TB/s 为产业共识）。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_006 | inference | 在位宽翻倍（2048-bit）与引脚速率提升（11.7~13.0 Gbps）的协同演进下，HBM4 单栈峰值带宽在报告中提升至 2.0~3.3 TB/s（M05 记述单堆栈带宽突破 2.0~3.0 TB/s 为产业共识）。 | M05:ch2-2:o2:0026 |  |  |
| task_001 | claim_007 | supported | HBM4 接口位宽翻倍与引脚互连演进伴随着底层工艺革新，包括引入 1µm 混合键合（取消传统微凸块）以及采用台积电先进制程（N3/N4/12nm）定制逻辑 Base Die。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_007 | supported | HBM4 接口位宽翻倍与引脚互连演进伴随着底层工艺革新，包括引入 1µm 混合键合（取消传统微凸块）以及采用台积电先进制程（N3/N4/12nm）定制逻辑 Base Die。 | M05:ch2-2:o2:0026 |  |  |
| task_009 | claim_001 | supported | 浸没式液冷是将整台服务器主板、CPU、GPU、内存及供电模块完全浸泡在不导电的绝缘介电液体（Dielectric Fluid）中的液冷技术方案。 | M07:ch4-1:0039 |  |  |
| task_009 | claim_002 | supported | 两相浸没式液冷在物理传热学上具备优良的传热特性，但在工业落地与供应链层面遭遇了全氟和多氟烷基物质（PFAS）环保规制禁令的制约。 | M07:ch4-2:0042 |  |  |
| task_009 | claim_003 | inference | 现有证据表明两相浸没式液冷受制于 PFAS 环保法规，而单相与两相浸没式在热力学换热参数、散热极限及冷却液供应链替代格局上的完整对比仍有待进一步补充直接证据。 | M07:ch4-1:0039 |  |  |
| task_009 | claim_003 | inference | 现有证据表明两相浸没式液冷受制于 PFAS 环保法规，而单相与两相浸没式在热力学换热参数、散热极限及冷却液供应链替代格局上的完整对比仍有待进一步补充直接证据。 | M07:ch4-2:0042 |  |  |
| task_018 | claim_001 | supported | GPU 单芯片功耗随着架构演进显著上升（A100 400W、H100 700W、B200 1,000W），导致传统风冷技术在 40–50 kW/机架处达到物理散热极限并失效。 | GPU产业技术源流与投资机会_最终报告:ch5-2:0024 |  |  |
| task_018 | claim_002 | supported | 微通道冷板换热技术能够使数据中心承受高达 150 kW~200 kW 的单机架功率密度，并将 PUE 压制在 1.05~1.15 的极优区间，液体冷却液（去离子水/乙二醇溶液）的体积热容约为空气的 3,500 倍，对流换热系数高达 5,000~15,000 W/(m²·K)。 | M06:ch1-2:o2:0008 |  |  |
| task_018 | claim_003 | supported | 浸没式液冷技术将整台服务器主板、CPU、GPU、内存及供电模块完全浸泡在不导电的绝缘介电液体（Dielectric Fluid）中进行热交换。 | M07:ch4-1:0039 |  |  |
| task_018 | claim_004 | supported | 冷却系统并未消灭热量，而是将高密度的热流转移至冷却水回路中；为了将 35°C~45°C 的温水废热排放至大气，采用机械制冷压缩机（Chiller）将消耗巨大压缩电能，采用蒸发冷却塔则引发水资源消耗硬约束（WUE 危机）。 | M06:ch1-2:o2:0008 |  |  |
| task_018 | claim_005 | inference | AI 算力扩张推升液冷需求的核心因果机制为：大算力芯片高 TDP 与高密度集群使得机架发热功率突破风冷散热极限（40–50 kW/机架），液冷凭借高体积热容与传热效率成为承载 150~200 kW 单机架密度与压降 PUE 的必由技术路线，驱动工业界向直接芯片液冷（DLC）与浸没式液冷全面迁移。 | GPU产业技术源流与投资机会_最终报告:ch5-2:0024 |  |  |
| task_018 | claim_005 | inference | AI 算力扩张推升液冷需求的核心因果机制为：大算力芯片高 TDP 与高密度集群使得机架发热功率突破风冷散热极限（40–50 kW/机架），液冷凭借高体积热容与传热效率成为承载 150~200 kW 单机架密度与压降 PUE 的必由技术路线，驱动工业界向直接芯片液冷（DLC）与浸没式液冷全面迁移。 | M06:ch1-2:o2:0008 |  |  |
| task_018 | claim_008 | inference | 面对电力与变压器交付瓶颈，行业存在通过算法效率（蒸馏/小模型）、SMR 核电与低功耗架构等技术替代轴打破增长物理上限的潜在演进路径。 | GPU产业技术源流与投资机会_最终报告:ch5-2:0024 |  |  |
| task_025 | claim_001 | supported | 根据报告规格表，HBM2E（2020年）、HBM3（2023年）及HBM3e（2024年）接口位宽均为1024-bit，Base Die采用DRAM标准工艺，核心封装工艺由Micro-bump TCB演进至MR-MUF/TC-NCF及Advanced MR-MUF，单栈峰值带宽由460 GB/s提升至1.2 TB/s。 | M04:ch3-2:o1:0040 |  |  |
| task_025 | claim_005 | supported | 根据TrendForce数据（位元出货口径），2025年全年HBM市场份额中SK海力士占52.3%、三星占28.7%、美光占19%。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |
| task_025 | claim_007 | supported | 根据TrendForce等数据，台积电在CoWoS先进封装领域独占90%以上份额，2023–2025年CoWoS产能为实际交付瓶颈（NVIDIA占用60%以上产能），其产能从2023年的13-15K wpm扩张至2025年的75-80K wpm。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |
| task_025 | claim_009 | inference | 结合两份证据推断，台积电占全球先进制程约70%并独占CoWoS封装90%以上；当HBM4 Base Die制造由传统DRAM工艺转向TSMC 12nm/3nm逻辑工艺时，HBM底层制造与系统级封装在代工节点上对台积电的依赖程度进一步加深。 | M04:ch3-2:o1:0040 |  |  |
| task_025 | claim_009 | inference | 结合两份证据推断，台积电占全球先进制程约70%并独占CoWoS封装90%以上；当HBM4 Base Die制造由传统DRAM工艺转向TSMC 12nm/3nm逻辑工艺时，HBM底层制造与系统级封装在代工节点上对台积电的依赖程度进一步加深。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |
| task_025 | claim_010 | supported | 报告指出除先进制程与先进封装外，互连（NVLink 5跨域通信带宽骤降与机架120 kW/1.4吨物理上限）构成了系统级第二短板。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |

---

注：本报告不调用模型，仅按 TaskPack Importer 八步 Gate 校验。
