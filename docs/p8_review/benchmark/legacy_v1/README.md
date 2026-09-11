# Legacy Golden v1（冻结，不可修改）

- **题数**：50
- **来源**：`D:/AI-Knowledge-Engine/data/golden_queries.jsonl`（引擎侧原始题集）
- **快照 SHA256**：`aa0412a24ccc30b6a0d75d97e4265b948b83bdb1c674db28f45eb17453973aea`
- **冻结时间**：2026-09-11（P8-0）

## 状态

依据 `_meta/P8_开发建议与执行规范_v1.0.md` §5.2 / §17：

> 现有 50 题**永远冻结、不得删除、不得修改**。用途转为 **Legacy Canary / Regression**，
> 不再承担唯一 production gate 的角色；新门线由 Development + Holdout 重建。

## 格式

每题含 `id / query / type / relevant_sections`，其中 `relevant_sections` 用
`{document_id, heading_contains, grade}` 锚定（section 级，`heading LIKE` 解析）。

## 已知局限（P8 交接说明 §8.1）

`heading_contains` 仅对旗舰（M 系列）语料成立：日报/OCR 类文档的 `heading`
多被自动截断或退化为占位标题（`元信息` / `图表（pN OCR）` / `配图N`）。
因此**新题集禁止沿用 heading 锚定**，必须固化 `chunk_id` 或锚定正文片段。

## 金标目标文档（全部为 D 盘旗舰归档）

`M04 M05 M06 M07 M09 M10 M16 M18 M22`（共 9 篇，均属 187 篇旗舰归档）。

> 这决定了 **旗舰隔离探针**可在 `document_ids = 187 篇归档` 的子集内完整评测全部 50 题的金标。
