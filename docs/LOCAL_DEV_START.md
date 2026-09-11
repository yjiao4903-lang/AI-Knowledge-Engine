# LOCAL-DEV Start Here

Role: **LOCAL-DEV**  
Project: `yjiao4903-lang/AI-Knowledge-Engine`  
Control: Issue #30  
Current task: Issue #32

## Required reading order

1. `/AGENTS.md`
2. `/docs/PROJECT_CONTROL.md`
3. GitHub Issue #30
4. GitHub Issue #32
5. `/docs/CURRENT_STATE.md`
6. `/docs/HANDOFF_PROTOCOL.md`
7. `/docs/P8_RETRIEVAL_QUALITY_REVIEW_20260911.md`
8. `/docs/p8_review/reports/P8_中期报告_WP1_WP2_20260911.md`

## Current assignment

Execute **Issue #32 — P8-ENG-01: reproduce and stabilize reconcile determinism**.

Work from authoritative `main`. Preserve unrelated local changes. Use branch:

`local-dev/32-reconcile-determinism`

First reproduce and record the nondeterministic reconcile/chunk-count behavior before changing code. Focus on the smallest reproduction around `M04` / `M09` / `_最终报告`.

Do not modify Legacy Golden, do not rewrite source corpus to make tests pass, and do not perform full-corpus destructive re-extraction/rechunk/reindex without explicit WEB-CONTROL authorization.

Return work through one PR linked to Issue #32 with exact-head SHA, reproduction evidence, tests and real local SQLite/Qdrant validation. Do not merge.

If Issue #32 conflicts with this file, **Issue #32 is authoritative for task scope**; `AGENTS.md` is authoritative for role and process boundaries.
