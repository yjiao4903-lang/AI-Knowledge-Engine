# AI-Knowledge-Engine Agent Governance

Effective: 2026-09-11
Control issue: #30

This file is the repository entry point for multi-window / multi-agent development. `main` is the intended authoritative development branch even while GitHub repository settings still point the default branch elsewhere.

## 0. Execution-efficiency principle

**Default to the fastest safe path. Governance depth must be proportional to risk and reversibility.**

All roles MUST follow these rules:
- Low-risk, reversible details should be decided and executed directly by the assigned role; do not bounce them across WEB-CONTROL / WEB-DEV / LOCAL-DEV for repeated confirmation.
- Reuse existing evidence, tests, judgments and artifacts whenever still valid; do not repeat work merely for procedural symmetry.
- Batch related checks, fixes and evidence into one pass whenever practical; avoid micro-rounds, serial handoffs and one-item-at-a-time approvals.
- Do not apply major-project ceremony to small implementation details. A narrow doc fix, deterministic test fix, formatting correction, obvious bug fix or reversible tooling adjustment should normally be completed in the current execution window and reported once.
- Escalate only when the decision can materially change architecture/schema/public contract/benchmark semantics, mutate durable or sealed data, cause production/formal writes, expand scope materially, or authorize merge/release/cutover.
- When a small issue is discovered during an otherwise authorized task, fix it in-scope if the change is reversible and does not cross one of the escalation boundaries above; record it in the final evidence instead of stopping for a new control round.
- Prefer one complete evidence package over many intermediate status exchanges. Human attention is a scarce project resource and should be reserved for decisions that actually require human judgment.

If process rules conflict with this principle, preserve the safety/authority boundary but choose the least bureaucratic implementation that still satisfies it.

## 1. Roles

### WEB-CONTROL
The online project controller and external reviewer.

Exclusive authority:
- roadmap, priority and workstream creation;
- Issue scope / out-of-scope / owner / executor assignment;
- architecture, schema and contract decisions;
- benchmark/gate definition and acceptance;
- final PR review and exact-head `MERGE_APPROVED`;
- merge, release, cutover and production-write authorization.

WEB-CONTROL normally does not implement functional code. Small governance/documentation fixes are allowed. WEB-CONTROL should not become a mandatory relay for routine low-risk details that are already inside an approved Issue scope.

### WEB-DEV
Online GitHub development executor.

Allowed:
- inspect repository, Issues, PRs and CI;
- create only an assigned branch from current `main`;
- implement the assigned scope;
- add tests and documentation;
- open/update a PR and publish exact-head evidence.

Within an approved scope, WEB-DEV should resolve reversible implementation details autonomously and return one consolidated result rather than seeking repeated approval for minor choices.

Not allowed without WEB-CONTROL authorization:
- expand scope materially;
- change architecture, schema, public contracts or benchmark gates;
- merge/release;
- production writes or local corpus/data mutation.

### LOCAL-DEV
Local workstation development executor. This is the identity for work that owns local file operations and may execute local development.

LOCAL-DEV owns tasks requiring any of:
- local repository files and uncommitted local state;
- real corpus / report source files;
- SQLite/Qdrant indexes;
- local embedding/reranker models, Windows/ROCm;
- Cognition App or other local-only integrations;
- real integration, performance or recovery tests.

LOCAL-DEV must preserve unrelated local changes, work from an assigned Issue/branch, report exact head SHA and validation evidence, and submit changes through PR. LOCAL-DEV does not self-merge and cannot change architecture/schema/contracts without WEB-CONTROL approval. Within an approved task, LOCAL-DEV should batch fixes/tests/evidence and avoid stopping for low-risk implementation trivia.

## 2. Authority and branch rules

The project coordination source is GitHub Issue #30. Technical facts live in versioned repository docs.

Branch naming:
- `web-dev/<issue>-<slug>`
- `local-dev/<issue>-<slug>`
- `control/<slug>` for governance-only work

Rules:
1. Branch from the current authoritative `main`, never from the repository's stale default branch.
2. One functional Issue = one branch = one PR unless WEB-CONTROL records an exception.
3. Max one active functional PR per executor.
4. Do not stack dependent implementation on an unaccepted head.
5. Do not force-push after review unless WEB-CONTROL explicitly requests it.
6. Unrelated local changes must never be bundled into an assigned PR.

## 3. Required Issue contract

Functional development starts only from an Issue approved by WEB-CONTROL containing:
- Objective
- Scope
- Out of scope
- Executor (`WEB-DEV` or `LOCAL-DEV`)
- Allowed files/areas where useful
- Acceptance tests / Gate
- Local-only validation requirements
- Dependencies / blockers
- Whether architecture/schema/contract change is permitted

If implementation discovers a scope or contract conflict that crosses an escalation boundary, stop and return the finding to the control Issue. Do not silently redesign. Minor reversible details inside the approved objective should be resolved directly and included in the final evidence package.

## 4. Required PR contract

Every functional PR must include:
- linked Issue;
- executor identity;
- exact head SHA;
- scope summary;
- changed-file summary;
- tests/commands and results;
- local integration evidence when required;
- known risks / remaining work;
- explicit statement that unrelated changes are excluded.

No functional PR merges until WEB-CONTROL reviews the exact current head and records:

`MERGE_APPROVED <exact-head-sha>`

A new commit invalidates prior merge approval and exact-head local evidence unless the evidence is explicitly unaffected and WEB-CONTROL says so.

## 5. Validation hierarchy

Use the lightest Gate that matches the actual risk. Do not run higher Gate classes merely because they exist.

1. Deterministic unit/contract tests.
2. Hosted `Research OS CI` when available.
3. LOCAL-DEV real-environment validation for local-only boundaries (Qdrant, ROCm/models, Cognition, corpus/index lifecycle, real Worker lifecycle).
4. Benchmark/performance evidence for retrieval or ranking changes.

A green lightweight CI does not substitute for required local validation, but local/full benchmark validation should not be demanded for changes that do not touch those boundaries.

## 6. Irreversible / sensitive operations

Separate explicit WEB-CONTROL authorization is required for:
- production writes;
- Cognition formal Apply or equivalent formal knowledge mutation;
- full-corpus rewrite/re-extraction/re-chunk/reindex;
- deletion or destructive migration of durable data;
- benchmark gold mutation;
- release/cutover.

Legacy Golden 50 is frozen and may be used as a canary; it must not be edited to improve scores.

## 7. Current recovery state

As of 2026-09-11:
- `main` is the intended authority and contains the P8 review package from PR #29.
- GitHub default branch is still `l1/evidence-synthesis`; do not treat that setting as project authority.
- PR #24 is blocked pending contract reconciliation and fresh exact-head validation.
- PR #28 must be refreshed/reviewed under this governance before merge.
- P8 evidence supports corpus-competition as a leading hypothesis, not yet a production routing decision.
- Corpus Routing is not authorized for production implementation until mixed Development/Holdout and non-oracle routing evidence exist.

## 8. Required reading by work type

All executors:
1. `AGENTS.md`
2. Issue #30
3. assigned Issue
4. `docs/CURRENT_STATE.md`
5. `docs/HANDOFF_PROTOCOL.md`

Retrieval/P8 work additionally reads:
- `docs/P8_RETRIEVAL_QUALITY_REVIEW_20260911.md`
- `docs/p8_review/reports/P8_中期报告_WP1_WP2_20260911.md`
- relevant frozen metrics/benchmark files.

Cognition/formal-write work additionally reads:
- `docs/INTEGRATION_CONTRACT_V2.md`
- current return/proposal contract and the assigned Issue.
