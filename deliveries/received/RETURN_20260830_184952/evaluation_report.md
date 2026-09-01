# TaskPack Evaluation Report（.）

日期：生成于运行时刻 ｜ 模型：外部 Worker（本报告只做无模型校验）
Golden 输入：`data/taskpack_golden/` ｜ Worker 结果：`data/taskpack_golden/runs/./`
N = 4 个任务包

## 汇总（§74 自动 Gate）

| Gate | 要求 | 本 Run |
|---|---|---|
| TaskPack Manifest 100% valid | =N | 4/4 |
| Result Schema 100% valid | =N | 4/4 |
| Citation Invalid Tasks | =0 | 0 |
| Citation Coverage >=95% | >=N | 4/4 |
| Unsupported Claim Rate <=5% | <=N | 4/4 |
| 全通过 | — | 4/4 |

## 逐任务指标

| task_id | manifest | schema | citation_invalid | cov | unsup | stale | 通过 | 失败 Gate |
|---|---|---|---|---|---|---|---|---|

| 20260830_180537_hbm4-hbm | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |
| 20260830_180537_task | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |
| 20260830_180537_ai | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |
| 20260830_180538_hbm | ✓ | ✓ | 0 | 100.0% | 0.0% | — | PASS |  |

## 人工 Entailment 审核表（§56）

需要人工标注：每行 evidence 是否 entail 该 claim（rides / supports / contradicts / unknown）与备注。

| task_id | claim_id | epistemic | claim_text | evidence_chunk_id | entailment | note |
|---|---|---|---|---|---|---|

| task_001 | claim_001 | supported | HBM4 相比前几代 HBM（HBM2E、HBM3、HBM3e 的 1024-bit）接口位宽实现翻倍，跃升至 2048-bit。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_001 | supported | HBM4 相比前几代 HBM（HBM2E、HBM3、HBM3e 的 1024-bit）接口位宽实现翻倍，跃升至 2048-bit。 | M05:ch2-2:o2:0026 |  |  |
| task_001 | claim_002 | supported | HBM 引脚速率呈现代际递增演进：HBM2E 为 3.6 Gbps、HBM3 为 6.4 Gbps、HBM3e 为 9.6 Gbps，至 HBM4 引脚速率提升至 11.7~13.0 Gbps。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_003 | supported | 在 2048-bit 接口位宽翻倍与引脚速率提升的共同驱动下，HBM4 单堆栈峰值带宽突破至 2.0 ~ 3.3 TB/s（M05 标注为突破 2.0 ~ 3.0 TB/s），显著高于 HBM3e（1.2 TB/s）、HBM3（819 GB/s）与 HBM2E（460 GB/s）。 | M04:ch3-2:o1:0040 |  |  |
| task_001 | claim_003 | supported | 在 2048-bit 接口位宽翻倍与引脚速率提升的共同驱动下，HBM4 单堆栈峰值带宽突破至 2.0 ~ 3.3 TB/s（M05 标注为突破 2.0 ~ 3.0 TB/s），显著高于 HBM3e（1.2 TB/s）、HBM3（819 GB/s）与 HBM2E（460 GB/s）。 | M05:ch2-2:o2:0026 |  |  |
| task_001 | claim_004 | supported | 后继规划代际 HBM4E 预计维持 2048-bit 接口位宽，引脚速率预计进一步提升至 14~16 Gbps，单栈峰值带宽预计达 3.6 ~ 4.0 TB/s。 | M04:ch3-2:o1:0040 |  |  |
| task_009 | claim_001 | supported | 浸没式液冷的工作机制是将整台服务器主板、CPU、GPU、内存及供电模块完全浸泡在不导电的绝缘介电液体（Dielectric Fluid）中。 | M07:ch4-1:0039 |  |  |
| task_009 | claim_002 | supported | 两相浸没式液冷在物理传热学上极为优雅，但遭遇了全氟和多氟烷基物质（PFAS）环保禁令带来的全球供应链冲击（如 3M 退出氟化液市场）。 | M07:ch4-2:0042 |  |  |
| task_018 | claim_001 | supported | AI 算力扩张推动 GPU 单芯片功耗剧增（A100 400W → H100 700W → B200 1,000W → Rubin 约 1,800W+），导致机架功率密度突破传统风冷 40–50 kW/机架的物理散热极限并失效。 | GPU产业技术源流与投资机会_最终报告:ch5-2:0024 |  |  |
| task_018 | claim_002 | supported | 液体冷却介质体积热容约为空气的 3,500 倍，对流换热系数高达 5,000 ~ 15,000 W/(m²·K)，微通道冷板可支持 150 ~ 200 kW 单机架超高密度并将 PUE 压制在 1.05 ~ 1.15 的极优区间。 | M06:ch1-2:o2:0008 |  |  |
| task_018 | claim_003 | supported | 在芯片功耗激增与风冷失效的直接驱动下，全球液冷渗透率从 2024 年的 14% 快速跃升至 2025 年的 33%，直接芯片液冷（DLC）与浸没式液冷成为工业界全面迁移的主流形态。 | GPU产业技术源流与投资机会_最终报告:ch5-2:0024 |  |  |
| task_018 | claim_003 | supported | 在芯片功耗激增与风冷失效的直接驱动下，全球液冷渗透率从 2024 年的 14% 快速跃升至 2025 年的 33%，直接芯片液冷（DLC）与浸没式液冷成为工业界全面迁移的主流形态。 | M06:ch1-2:o2:0008 |  |  |
| task_018 | claim_003 | supported | 在芯片功耗激增与风冷失效的直接驱动下，全球液冷渗透率从 2024 年的 14% 快速跃升至 2025 年的 33%，直接芯片液冷（DLC）与浸没式液冷成为工业界全面迁移的主流形态。 | M07:ch4-1:0039 |  |  |
| task_018 | claim_004 | inference | AI 算力扩张推升液冷需求的因果链条表现为：算力增长驱动芯片 TDP 跃升并突破风冷散热物理硬约束，迫使数据中心转向具备数千倍换热能力的高效液冷架构以承载高密算力部署并压降 PUE。 | GPU产业技术源流与投资机会_最终报告:ch5-2:0024 |  |  |
| task_018 | claim_004 | inference | AI 算力扩张推升液冷需求的因果链条表现为：算力增长驱动芯片 TDP 跃升并突破风冷散热物理硬约束，迫使数据中心转向具备数千倍换热能力的高效液冷架构以承载高密算力部署并压降 PUE。 | M06:ch1-2:o2:0008 |  |  |
| task_025 | claim_001 | supported | HBM 代际迭代显著提升了封装复杂度与制造价值：HBM4 单栈位宽翻倍至 2048-bit，引入 TSMC 12nm/3nm 定制逻辑 Base Die 与 1µm 混合键合；HBM 市场总规模（TAM）从 2023 年 44 亿美元爆发式增长至 2026 年预计 540-570 亿美元。 | M04:ch3-2:o1:0040 |  |  |
| task_025 | claim_001 | supported | HBM 代际迭代显著提升了封装复杂度与制造价值：HBM4 单栈位宽翻倍至 2048-bit，引入 TSMC 12nm/3nm 定制逻辑 Base Die 与 1µm 混合键合；HBM 市场总规模（TAM）从 2023 年 44 亿美元爆发式增长至 2026 年预计 540-570 亿美元。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |
| task_025 | claim_002 | supported | 在 NVIDIA B200 芯片中，HBM 成本约 2,900 美元，占总制造成本（COGS 约 6,250-6,400 美元）的约 45%，但在终端售价中仅占约 7-9%。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |
| task_025 | claim_003 | supported | 台积电独占 CoWoS 先进封装 >90% 份额，产能从 2023 年 13-15K wpm 扩张至 2025 年 75-80K wpm（2026E 预计 115-140K wpm），在 2023–2025 年持续构成实际交付瓶颈，且 NVIDIA 占用超过 60% 产能。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |
| task_025 | claim_004 | supported | 2025 年 HBM 出货由 SK 海力士（52.3%）、三星（28.7%）、美光（19%）瓜分；2026 年虽有三星与美光通过认证形成 HBM4 三供，但 SK 海力士仍预计占据下一代 Rubin 平台 HBM4 约 70% 的供应份额。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |
| task_025 | claim_005 | inference | HBM4 将 Base Die 转向台积电 12nm/3nm 先进制程逻辑工艺，使得存储制造与台积电晶圆代工（先进制程占 ~70%）及 CoWoS 封装进一步深度绑定，加剧了单点供应链集中瓶颈。 | M04:ch3-2:o1:0040 |  |  |
| task_025 | claim_005 | inference | HBM4 将 Base Die 转向台积电 12nm/3nm 先进制程逻辑工艺，使得存储制造与台积电晶圆代工（先进制程占 ~70%）及 CoWoS 封装进一步深度绑定，加剧了单点供应链集中瓶颈。 | GPU产业技术源流与投资机会_最终报告:ch3-1:0014 |  |  |

---

注：本报告不调用模型，仅按 TaskPack Importer 八步 Gate 校验。
