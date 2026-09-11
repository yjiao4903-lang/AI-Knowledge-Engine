# P8 混合题集覆盖与校验报告

- Development: n=20 pass=True
- Holdout: n=10 pass=True (sealed, in_repo=False)
- Legacy 50: n=50 frozen_sha_ok=True
- Leakage (dev∩holdout target docs): 0

## 分层覆盖

| tier | dev | dev% | holdout | holdout% |
|---|---|---|---|---|
| broker_report | 4 | 20.0% | 2 | 20.0% |
| daily_report | 3 | 15.0% | 2 | 20.0% |
| discussion | 2 | 10.0% | 1 | 10.0% |
| flagship | 5 | 25.0% | 2 | 20.0% |
| research_media | 3 | 15.0% | 2 | 20.0% |
| trading_desk | 3 | 15.0% | 1 | 10.0% |

## 题型覆盖

| query_type | dev | holdout |
|---|---|---|
| comparison | 3 | 2 |
| entity_context | 2 | 1 |
| mechanism | 4 | 2 |
| multi_evidence | 3 | 1 |
| numeric | 5 | 3 |
| temporal | 3 | 1 |
