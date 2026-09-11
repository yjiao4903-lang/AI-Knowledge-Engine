# LOCAL-DEV Start Here

Role: **LOCAL-DEV**  
Project: `yjiao4903-lang/AI-Knowledge-Engine`  
Control: Issue #30  
Current task: Issue #36

## Required reading order

1. `/AGENTS.md`
2. `/docs/PROJECT_CONTROL.md`
3. GitHub Issue #30
4. GitHub Issue #36
5. `/docs/CURRENT_STATE.md`
6. `/docs/HANDOFF_PROTOCOL.md`
7. `/docs/P8_RETRIEVAL_QUALITY_REVIEW_20260911.md`
8. `/docs/p8_review/reports/P8_中期报告_WP1_WP2_20260911.md`
9. `/docs/p8_review/reports/P8_ENG01_RECONCILE_DETERMINISM_20260911.md`

## Current assignment

Execute **Issue #36 — P8-BENCH-01: build mixed Development / sealed Holdout benchmark**.

P8-ENG-01 is complete: PR #35 fixed the doc_id/reconcile determinism defect and is merged into authoritative `main`.

Work from current authoritative `main`. Preserve unrelated local changes. Use branch:

`local-dev/36-p8-mixed-benchmark`

The goal is measurement quality, not retrieval optimization. Build a representative **Development 150 + sealed Holdout 150** benchmark spanning the real corpus and realistic query types. Legacy 50 remains byte-for-byte frozen as a canary.

Do not implement Corpus Routing, tune retrieval weights, upgrade the reranker, mutate Legacy Golden, or perform destructive full-corpus rewrite/re-extraction/rechunk/reindex under this task.

The public repository may contain Development gold and Holdout freeze/hash/composition metadata, but the full Holdout question/gold content must remain sealed locally until WEB-CONTROL authorizes final evaluation disclosure.

Return work through one PR/evidence package linked to Issue #36 with exact-head SHA, deterministic generation/validation evidence, split/leakage checks, Development baseline metrics, Holdout aggregate metrics/confidence intervals, and proof that Legacy 50 is unchanged. Do not merge.

If Issue #36 conflicts with this file, **Issue #36 is authoritative for task scope**; `AGENTS.md` is authoritative for role and process boundaries.
