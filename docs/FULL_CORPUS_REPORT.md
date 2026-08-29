# Full Corpus Report（I0 全量语料 Gate 报告）

> 生成：2026-08-30 ｜ 配置：`config/config.full.yaml`（catalog_full.db + kb_chunks_full_v1/kb_sections_full_v1）
> 知识源：`D:\AI深度报告归档`（只读）｜ 收录策略：ADR-013 v2（仅终版报告）
> 配套数据：`data/full_corpus_stats.json` / `data/full_corpus_failures.json`(=last_scan.json) /
> `data/full_corpus_sample.json` / `data/full_corpus_regression.json` / `data/full_corpus_preflight.json`

## 1. 索引统计（主计划 §11）

| 项 | 值 |
|---|---|
| Total Files Scanned (md) | 7159（127.8 MB） |
| Indexed / Parsed Files | **189**（9.6 MB，全部为终版报告） |
| Skipped Files | 6970（全部带 Exclusion Reason，见下） |
| Failed Files | **0** ｜ Encoding Failures **0** ｜ Parser Fatal Rate **0%**（阈值 ≤0.5%） |
| Total Sections | 8828 |
| Total Chunks | **9780** |
| FTS Terms / FTS Trigram / Qdrant Points | **9780 / 9780 / 9780** |
| Qdrant Sections Points | 8987（159 点为 v1 策略残段，见 Known Issues） |
| Duplicate Document IDs（catalog 内） | 0 ｜ 消歧 ID 2 个 |
| Oversized Chunks (> hard_max 2200 字符) | 18（chunker soft-limit 语义内的整表保留块，非异常） |
| Parser / Chunker Warnings | 无告警通道（v0.1.0/v0.3.0 结构性保证，硬失败计入 Failed=0） |

### 排除明细（Exclusion Reason + Count，无静默丢弃）

| Reason | Count | 内容 |
|---|---|---|
| EXCLUDED_DIR | 6413 | 研究输出（工作层过程稿）、_废弃_旧镜像、版本存档、03_历史版本存档、根级冗余、research-expert-team、.agents |
| EXCLUDED_NON_FINAL | 339 | 非终版成品：思维增量/负知识/审核意见/草稿/参数卡/overview/分章报告/库级元文档 |
| EXCLUDED_PROCESS | 191 | 阶段文件（stem 00-10 段 + 开题报告） |
| EXCLUDED_DUPLICATE | 27 | 02 成品层与旗舰备份内容完全相同的拷贝（sha256 验证，保留 02 canonical） |

依据：归档自身权威索引 `00_归档索引.md` V3.1 的成品层定义（189 主题）。
放宽策略后重扫即可增量收录（未索引文件以 NEW 拾取），无重建成本。

## 2. 一致性 Gate（主计划 §12）

**PASS**：`chunks 9780 = fts_terms 9780 = fts_trigram 9780 = qdrant_points 9780`
（`reindex.py check` 逐文档四方计数全 ok；首次发现 347 个 v1 残留孤儿点，已由
`reindex.py repair` 清除并复核。）

## 3. 人工抽样核对（主计划 §13）

随机 100 篇（seed=20260829，可复现），逐篇独立复验（不复用索引数据）：
UTF-8 编码 / metadata 回读 / heading tree 一致 / 行号边界 / chunks 非空与行号 /
表格内容落块（归一化比对，兼容 ADR-007 类型继承）/ reference/audit 对账。

**结果：100/100 PASS**（初跑 2 例表格误报为校验脚本过严，已修正校验逻辑并复核）。

## 4. 全库 Golden Regression（主计划 §14）

50 条人工章节级标注 × 7-arm，直接对生产全量索引（非临时语料）：

| Arm | Hit@5 | MRR@10 | NDCG@10 | P50/P95 ms |
|---|---|---|---|---|
| terms | 0.560 | 0.412 | 0.456 | 0/0 |
| trigram | 0.460 | 0.324 | 0.359 | 0/0 |
| lexical | 0.580 | 0.422 | 0.485 | 4.1/7.2 |
| dense | 0.780 | 0.625 | 0.647 | 40.8/63.0 |
| hybrid | 0.800 | 0.627 | 0.653 | 45.4/65.5 |
| hybrid_boost | 0.800 | 0.624 | 0.657 | 90.5/110.8 |
| **hybrid_rerank** | **0.920** | **0.765** | **0.801** | 1029.9/1400.6 |

Gate：Hit@5 0.920≥0.90 ✅ ｜ MRR 0.765≥0.75 ✅ ｜ NDCG 0.801≥0.80 ✅ ｜
Exact 1.00≥0.95 ✅ ｜ Semantic 1.00≥0.85 ✅ ｜ **GATE PASS**

- 50/50 Golden 标注全量解析成功（dev 10 篇 fixture 与归档终版 sha256 一致）
- 失败 4 条：C01 BAD_FUSION；C03/R01/X01 全库稀释下排序下降——交接方
  HANDOFF_I0 §3 预期的「全库出现同名 section / 同源稀释」语义变化，如实记录
- 对比 dev 基线（Hit@5 0.96/MRR 0.869/NDCG 0.897）：全库 189 篇下小幅稀释
  但全部阈值仍满足；单路 lexical/ dense 下降幅度较大符合规模预期

## 5. I0 Gate 汇总（HANDOFF_I0 §2）

```
[x] Full Corpus Index PASS（一致性四方相等 + 抽样 100/100）
[x] Full Corpus Golden Regression PASS（五项阈值全过）
[x] Parser Fatal Rate 0% <= 0.5%，No Silent Data Loss（排除全量留档）
[x] Integration Contract V1（D:\AI知识整合体系\docs\INTEGRATION_CONTRACT.md）
[x] EvidenceReference V1（同上 §3）
[x] documents/{id}/chunks 端点 + 测试（pytest 114 passed，基线只增不减）
[x] Health / Error Model（index_generation + gpu_worker + 503 语义）
[x] INTEGRATION_READINESS.md / FULL_CORPUS_REPORT.md / stats / failures 产出齐全
```

## 6. Known Issues（I0 新增）

1. kb_sections_full_v1 含 159 个 v1 策略残段（sections 不在四方 Gate 内；chunks 已 repair）。
   后续可对 sections collection 执行一次按 document_id 的重建清理（低风险，I1 前完成）。
2. 收录策略变更后 rescan 不会自动删除被新策略排除的已索引文档（本次以清库重扫解决）；
   已在 docid_policy 文档中记录为已知限制。
3. 18 个 oversized chunks（>2200 字符）为整表保留块（keep_tables_whole 语义），非缺陷。
4. 真实语料暴露并修复解析器缺陷：复合中文数字（第十一章→ch0 撞名）导致 sections
   UNIQUE 冲突，无法索引——修复 `_cn_to_int` + section_id 撞名兜底（:x{n} 后缀）。

## 7. ADR 变更

- **ADR-013 全量语料收录与 doc_id 策略**（v2 仅终版）：见
  `backend/app/indexing/docid_policy.py` 模块文档与 INTEGRATION_CONTRACT.md §6。
- **ADR-014 解析器复合中文数字支持**：_cn_to_int 支持一~九十九；section_id 撞名
  兜底追加 :x{n}。parser_version 0.1.0（行为增量化，不影响既有 dev 语料 ID）。
- **ADR-015 配置切换机制**：load_config 支持 KE_CONFIG 环境变量与 --config；
  config.yaml=生产（全量），config.dev.yaml=dev 留档。
