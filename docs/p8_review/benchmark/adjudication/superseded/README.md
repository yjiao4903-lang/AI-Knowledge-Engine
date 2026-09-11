# 已作废批次（superseded）— 仅作历史/调试，**不计入**人工校准门线

## 作废对象

- `development_calibration_v1/`（Dev 20 题盲化人审包，packet sha256 `56357c37…`）
- `_keys/key_development_calibration_v1.json`（Dev 盲化映射）
- 仓库外密封对应件：`E:\研报提取资料库\_golden\p8_bench02_adjudication\superseded\holdout_calibration_v1\`
  与 `...\superseded\_keys\key_holdout_calibration_v1.json`（sealed Holdout 10 题）

## 作废原因（2026-09-11 WEB-CONTROL 控制决定）

领域审阅者反馈：**在未读过源报告的情况下，多条 query 无法被可复现地理解与判定**。它们依赖隐藏的
源报告上下文，例如未定义的「报告中」「相关指标」「数量上的差异」「作用」等指代/泛化维度。
因此该批次不是有效的人工判定输入 —— 审阅者只能靠猜测作者意图来给分。

**决定**：该批次从人工校准门线中**撤回**，不再要求审阅者继续判定。它保留在此仅作历史与调试用途。

## 强制标记

两个 key 文件中已写入：

```json
"withdrawn": {
  "reason": "...",
  "superseded_by": "...development_calibration_v2...",
  "counts_toward_human_review_complete": false
}
```

`p8_bench_adjudicate.py import` 遇到带 `withdrawn` 标记的 key 会**直接拒绝执行**，除非显式加
`--allow-withdrawn`（仅限本地调试）。因此本批次**不可能**被计入 `human_review_complete`。

## 替代批次

见 `../development_calibration_v2/`（Dev 20）与仓库外密封的
`E:\研报提取资料库\_golden\p8_bench02_adjudication\v2\holdout_calibration_v2\`（sealed Holdout 10），
二者均先通过 **Query Validity Gate**（`../query_validity_audit_v2.json`：Dev 20/20、Holdout 10/10）。
