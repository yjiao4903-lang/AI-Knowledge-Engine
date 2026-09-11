# LOCAL-DEV Start Here

Role: **LOCAL-DEV**  
Project: `yjiao4903-lang/AI-Knowledge-Engine`  
Control: Issue #30  
Current task: Issue #39

## Required reading order

1. `/AGENTS.md`
2. `/docs/PROJECT_CONTROL.md`
3. GitHub Issue #30
4. GitHub Issue #39
5. `/docs/CURRENT_STATE.md`
6. `/docs/HANDOFF_PROTOCOL.md`
7. `/docs/P8_RETRIEVAL_QUALITY_REVIEW_20260911.md`
8. `/docs/p8_review/reports/P8_BENCH01_STATUS_20260911.md`
9. `/docs/p8_review/scripts/p8_bench_build.py`
10. `/docs/p8_review/scripts/p8_bench_verify.py`

## Current assignment

Execute **Issue #39 — P8-BENCH-02: human-in-the-loop benchmark pilot with pooled relevance judging**.

P8-BENCH-01 is closed as a valid limiting-factor diagnosis: PR #38 established reusable benchmark tooling but proved that broad machine-authored entity prompts plus single-chunk gold are not gate-quality.

Work from current authoritative `main`. Preserve unrelated local changes. Use branch:

`local-dev/39-p8-benchmark-pilot`

Build only the **60 Development + 40 sealed Holdout pilot** defined in Issue #39. Use claim/context-specific questions and pooled graded relevance judging; every accepted query must have a defensible relevance set and false-negative audit before metrics are frozen.

Do not scale to 150+150 yet. Do not implement Corpus Routing, tune retrieval weights, upgrade the reranker, mutate Legacy Golden, or perform destructive corpus/reindex operations.

The full Holdout question/gold content must remain sealed outside the public repository. Return one PR/evidence package linked to Issue #39 with exact-head SHA and all required quality evidence. Do not merge.

If Issue #39 conflicts with this file, **Issue #39 is authoritative for task scope**; `AGENTS.md` is authoritative for role and process boundaries.
