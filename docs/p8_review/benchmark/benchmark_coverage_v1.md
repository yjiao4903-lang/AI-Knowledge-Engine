# P8 混合题集覆盖与校验报告

- Development: n=150 pass=True
- Holdout: n=150 pass=True (sealed, in_repo=False)
- Legacy 50: n=50 frozen_sha_ok=True
- Leakage (dev∩holdout target docs): 0

## 分层覆盖

| tier | dev | dev% | holdout | holdout% |
|---|---|---|---|---|
| broker_report | 30 | 20.0% | 30 | 20.0% |
| daily_report | 25 | 16.7% | 25 | 16.7% |
| discussion | 25 | 16.7% | 25 | 16.7% |
| flagship | 30 | 20.0% | 30 | 20.0% |
| research_media | 25 | 16.7% | 25 | 16.7% |
| trading_desk | 15 | 10.0% | 15 | 10.0% |

## 题型覆盖

| query_type | dev | holdout |
|---|---|---|
| causal | 20 | 20 |
| cross_doc | 20 | 20 |
| exact_entity | 25 | 25 |
| exact_number | 25 | 25 |
| long_tail | 15 | 15 |
| semantic_thesis | 30 | 30 |
| temporal | 15 | 15 |
