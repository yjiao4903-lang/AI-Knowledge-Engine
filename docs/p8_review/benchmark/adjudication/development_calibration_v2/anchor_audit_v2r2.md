# Dev20 authored-anchor inclusion audit（v2 packet r2）

- total queries：**20**
- missing authored anchor（旧 packet）：**2/20** → ['DEV2-17', 'DEV2-19']
- missing authored anchor（新 packet）：**0/20**
- 锚点被至少一个视图召回：18 / 20
- 锚点未被任何视图召回、强制纳入 judging pool：2 / 20 → ['DEV2-17', 'DEV2-19']

## needs human re-review（不模型补判）

- `DEV2-17`
- `DEV2-19`

## safe to reuse existing human judgments

- `DEV2-01`
- `DEV2-02`
- `DEV2-03`
- `DEV2-04`
- `DEV2-05`
- `DEV2-06`
- `DEV2-07`
- `DEV2-08`
- `DEV2-09`
- `DEV2-10`
- `DEV2-11`
- `DEV2-12`
- `DEV2-13`
- `DEV2-14`
- `DEV2-15`
- `DEV2-16`
- `DEV2-18`
- `DEV2-20`

## per-query anchor membership

| qid | anchor in old packet | anchor in new packet | recalled views | packet unchanged | judgment |
|---|---|---|---|---|---|
| `DEV2-01` | ✅ | ✅ | lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-02` | ✅ | ✅ | lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-03` | ✅ | ✅ | dense,lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-04` | ✅ | ✅ | dense,lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-05` | ✅ | ✅ | lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-06` | ✅ | ✅ | dense,hybrid | yes | reuse |
| `DEV2-07` | ✅ | ✅ | dense,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-08` | ✅ | ✅ | dense,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-09` | ✅ | ✅ | dense,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-10` | ✅ | ✅ | dense,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-11` | ✅ | ✅ | dense,lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-12` | ✅ | ✅ | lexical,hybrid | yes | reuse |
| `DEV2-13` | ✅ | ✅ | dense,lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-14` | ✅ | ✅ | dense,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-15` | ✅ | ✅ | dense | yes | reuse |
| `DEV2-16` | ✅ | ✅ | dense,lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-17` | ❌ | ✅ | none (forced) | CHANGED | re-review |
| `DEV2-18` | ✅ | ✅ | dense,lexical,hybrid,hybrid_rerank | yes | reuse |
| `DEV2-19` | ❌ | ✅ | none (forced) | CHANGED | re-review |
| `DEV2-20` | ✅ | ✅ | dense,lexical,hybrid,hybrid_rerank | yes | reuse |

## hashes

- packet_before: `889d6ee04bb0403f570719dd0d31f23d5ac42340c24aee0e6151fdec27fc74d0`
- key_before: `ed82bf35cc199da13f4b9b9f19dda92b89dbfb03115d7d5ff62a2a9dd31815b7`
- manifest_before: `040e2112ddfdcacd2586716da1f416b9de57851bfbfae4be2cfc32c3b835a568`
- packet_after: `4cf9a91afbf459c4711212bbef0e9da213dfa860ae409d0a4b51a1b8d971201d`
- key_after: `58e7e1c87a9b3b24ed938da6b876a6f1de96837c7d4731759cf862b94063e70f`
- manifest_after: `47fed9281f4ed2ff5b879f2203cad44a7196831a25b676b4bbec4b60bcaa209e`
- frozen_questions: `5b311e4aee3cf6a563668ad9b228439425e154a3b1e115e5935d959890739976`
- migration_report: `88a07a2101b14a495ba29dc28692e88f4e9fdec459cc304191366953993500eb`

## notes

- 未使用任何检索 rank/score 调整 query、retrieval weights、reranker 或 routing（仅 benchmark integrity audit）。
- query 文本、语料、检索行为、Legacy 50 均未改变。
- 诊断（不在本轮修复范围）：另有 10 个非锚点 auto_prelabel gold chunk 分布在 7 个 qid 中、未被任何视图召回且因此不在人审池（DEV2-06 6 个）。其效果是保守的（把检索命中的相关块当不相关），与锚点缺失造成的 survivor bias 方向相反；是否扩展强制纳入范围由 WEB-CONTROL 决定。
