# 旗舰隔离探针 · 逐题对照

同一批 50 题，同一金标；仅将检索域从**全库 3,566 篇**收窄到**D 盘旗舰归档 187 篇**。
full = /api 全库；flag = 旗舰隔离。“-”表示该层未出现 gold。

- 全库 hybrid_rerank：Hit@5 **0.82** / MRR 0.64 / NDCG 0.678
- 旗舰 hybrid_rerank：Hit@5 **0.9** / MRR 0.752 / NDCG 0.787
- ΔHit@5 **+0.08** ｜ ΔMRR +0.112 ｜ ΔNDCG +0.109
- 题级候选存在率：union50 0.96 → 1.0；fusion30 0.84 → 0.94
- NO_RECALL：2 → 0

## 判定

**H1（语料竞争压制排序）：成立**

隔离后 Hit@5 回升 +0.080，NO_RECALL 2→0，union50 题级存在率 0.96→1.0。竞争是主要退化来源，但隔离集内仍有 5 题失败（融合/重排残余），非纯竞争问题。

- 仅靠隔离即恢复前 5：**['S01', 'W01', 'O02', 'X03']**
- 隔离后仍失败：**['E02', 'C01', 'C03', 'R01', 'X01']**（属融合/重排/chunk/金标残余）

## 逐题对照（仅列任一环境失败的题）

| id | type | 层 | full | flag |
|---|---|---|---|---|
| E02 | exact | dense_rank | - | - |
| E02 | exact | terms_rank | - | - |
| E02 | exact | trigram_rank | 6 | 2 |
| E02 | exact | union50_rank | 106 | 101 |
| E02 | exact | fused_rank | 65 | 49 |
| E02 | exact | rerank_input_pos | - | - |
| E02 | exact | final_rank | - | - |
| E02 | exact | bucket | FUSION | FUSION |
| S01 | semantic | dense_rank | 37 | 19 |
| S01 | semantic | terms_rank | 3 | 2 |
| S01 | semantic | trigram_rank | - | - |
| S01 | semantic | union50_rank | 37 | 19 |
| S01 | semantic | fused_rank | 7 | 8 |
| S01 | semantic | rerank_input_pos | 7 | 8 |
| S01 | semantic | final_rank | - | 4 |
| S01 | semantic | bucket | RERANK | OK |
| C01 | causal | dense_rank | 34 | 28 |
| C01 | causal | terms_rank | 16 | 11 |
| C01 | causal | trigram_rank | - | - |
| C01 | causal | union50_rank | 34 | 28 |
| C01 | causal | fused_rank | 40 | 39 |
| C01 | causal | rerank_input_pos | - | - |
| C01 | causal | final_rank | - | - |
| C01 | causal | bucket | FUSION | FUSION |
| C03 | causal | dense_rank | 20 | 12 |
| C03 | causal | terms_rank | - | - |
| C03 | causal | trigram_rank | - | - |
| C03 | causal | union50_rank | 20 | 12 |
| C03 | causal | fused_rank | 33 | 24 |
| C03 | causal | rerank_input_pos | - | 24 |
| C03 | causal | final_rank | - | 8 |
| C03 | causal | bucket | FUSION | RERANK |
| W01 | monitoring | dense_rank | - | 11 |
| W01 | monitoring | terms_rank | - | 20 |
| W01 | monitoring | trigram_rank | - | - |
| W01 | monitoring | union50_rank | - | 11 |
| W01 | monitoring | fused_rank | - | 16 |
| W01 | monitoring | rerank_input_pos | - | 16 |
| W01 | monitoring | final_rank | - | 2 |
| W01 | monitoring | bucket | NO_RECALL | OK |
| O02 | overview | dense_rank | - | 47 |
| O02 | overview | terms_rank | 29 | 27 |
| O02 | overview | trigram_rank | - | - |
| O02 | overview | union50_rank | 71 | 47 |
| O02 | overview | fused_rank | 62 | 15 |
| O02 | overview | rerank_input_pos | - | 15 |
| O02 | overview | final_rank | - | 1 |
| O02 | overview | bucket | FUSION | OK |
| R01 | reference | dense_rank | - | 12 |
| R01 | reference | terms_rank | - | - |
| R01 | reference | trigram_rank | 16 | 16 |
| R01 | reference | union50_rank | 110 | 12 |
| R01 | reference | fused_rank | 97 | 10 |
| R01 | reference | rerank_input_pos | - | 10 |
| R01 | reference | final_rank | - | 7 |
| R01 | reference | bucket | FUSION | RERANK |
| X01 | cross_document | dense_rank | 24 | 19 |
| X01 | cross_document | terms_rank | - | - |
| X01 | cross_document | trigram_rank | - | - |
| X01 | cross_document | union50_rank | 24 | 19 |
| X01 | cross_document | fused_rank | 36 | 31 |
| X01 | cross_document | rerank_input_pos | - | - |
| X01 | cross_document | final_rank | - | - |
| X01 | cross_document | bucket | FUSION | FUSION |
| X03 | cross_document | dense_rank | - | 1 |
| X03 | cross_document | terms_rank | - | 6 |
| X03 | cross_document | trigram_rank | - | - |
| X03 | cross_document | union50_rank | - | 1 |
| X03 | cross_document | fused_rank | - | 2 |
| X03 | cross_document | rerank_input_pos | - | 2 |
| X03 | cross_document | final_rank | - | 1 |
| X03 | cross_document | bucket | NO_RECALL | OK |