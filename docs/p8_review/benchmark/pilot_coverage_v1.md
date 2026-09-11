# P8 混合题集覆盖与校验报告

- Development: n=60 pass=True
- Holdout: n=40 pass=True (sealed, in_repo=False)
- Legacy 50: n=50 frozen_sha_ok=True
- Leakage (dev∩holdout target docs): 0

## 分层覆盖

| tier | dev | dev% | holdout | holdout% |
|---|---|---|---|---|
| broker_report | 6 | 10.0% | 4 | 10.0% |
| daily_report | 7 | 11.7% | 6 | 15.0% |
| discussion | 6 | 10.0% | 5 | 12.5% |
| flagship | 11 | 18.3% | 7 | 17.5% |
| research_media | 9 | 15.0% | 14 | 35.0% |
| trading_desk | 21 | 35.0% | 4 | 10.0% |

## 题型覆盖

| query_type | dev | holdout |
|---|---|---|
| comparison | 7 | 7 |
| entity_context | 2 | 2 |
| mechanism | 17 | 14 |
| multi_evidence | 7 | 4 |
| numeric | 10 | 4 |
| temporal | 17 | 9 |
