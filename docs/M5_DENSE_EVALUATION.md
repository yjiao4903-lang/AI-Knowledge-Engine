# M5 Dense Evaluation Report

日期：2026-08-29 19:18
设备：cuda:1（rocm）—— 按 preferred_gpu_name 匹配: AMD Radeon RX 7900 XTX (cuda:1)；其余设备（含 iGPU）已排除
索引：kb_chunks_v1 = 407 points（407 chunks / 5 docs），kb_sections_v1 同步建立

## Semantic Rewrite Queries（Addendum §31）

Hit = Top5 chunk 的 plain_text 含任一预期关键词。

| Query | Hit@5 | Top1 Hit | embed ms | Top1 chunk |
|---|---|---|---|---|
| 为什么大型 AI GPU 对先进封装越来越依赖？ | True | True | 1358.5 | M04:ch5-3:o2:0067 |
| 为什么先进光刻反而可能降低大芯片经济性？ | True | True | 28.4 | M04:ch2-2:o2:0028 |
| 为什么越先进的光刻机反而可能对超大 GPU 不划算 | True | True | 28.4 | M04:ch2-2:o2:0028 |
| 玻尔兹曼极限是多少 | True | False | 27.3 | M04:top58:o59:0077 |
| HBM4 的接口位宽是多少 | True | True | 28.8 | M04:ch3-2:o1:0040 |
| AI 是否消除了半导体周期 | True | True | 28.8 | M04:ch5-2:0063 |
| 日本半导体的能力陷阱是什么 | True | False | 26.5 | M04:ch4-1:0051 |
| 数据中心为什么受到电网的制约 | True | False | 26.3 | M06:ch2-2:o2:0023 |
| 液冷为什么成为高密算力基础设施的必然 | True | True | 29.9 | M06:ch1-2:o2:0008 |
| Transformer 架构的上下文长度瓶颈在哪里 | True | True | 29.0 | M09:top1:o2:o4:0002 |

**Dense Hit@5 = 1.00　Top1 命中率 = 0.70**

## 延迟

| 指标 | P50 | P95 |
|---|---|---|
| query embed+search (ms) | 28.8 | 1358.5 |

## CPU Fallback（Addendum §32）

- CPU 单条 query embed：32106 ms（GPU 约为 P50 水平的 1/1114）
- Provider 在 cpu 设备加载并推理正常：PASS

## Gate（Addendum §32）

- Qwen Embedding smoke PASS（M0）
- RX 7900 XTX device PASS：preferred_gpu_name 匹配 cuda:1
- CPU fallback PASS
- Qdrant insert PASS：407 points
- Qdrant search PASS
- Semantic Query 基本命中：Hit@5 = 1.00
