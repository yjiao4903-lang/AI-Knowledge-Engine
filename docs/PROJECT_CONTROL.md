# AI-Knowledge-Engine Project Control

Effective: 2026-09-11  
Controller: `WEB-CONTROL`  
Online board: GitHub Issue #30

## 0. Execution-efficiency rule

Project control must optimize for **decision quality per unit of human attention**, not procedural volume.

Default behavior:
- use the lightest governance/Gate that matches the actual risk and reversibility;
- low-risk reversible details stay with the assigned executor and should be completed without repeated WEB-CONTROL round-trips;
- batch related checks, fixes, reviews and evidence into one pass;
- reuse still-valid evidence instead of repeating work for formality;
- do not apply major-project ceremony to small implementation/documentation/test details;
- escalate only for material scope expansion, architecture/schema/public-contract/benchmark-semantic changes, durable or sealed data mutation, production/formal writes, or merge/release/cutover authorization.

A process that is technically correct but repeatedly consumes human review for trivial reversible details is considered inefficient and should be simplified.

## 1. Operating model

The project uses three execution identities:

| Role | Environment | Primary responsibility | May merge? |
|---|---|---|---|
| WEB-CONTROL | GitHub / online | roadmap, scope, architecture decisions, Gate, final review | authorizes merge |
| WEB-DEV | GitHub / online | assigned model-free/code/documentation development | no |
| LOCAL-DEV | user workstation | local corpus/index/model/Cognition development and real validation | no |

`AGENTS.md` is the normative role/permission entry point.

## 2. Sources of truth

Use the following precedence when statements conflict:

1. Explicit current user instruction.
2. `AGENTS.md` role and permission boundaries.
3. GitHub Issue #30 and the assigned work Issue for scope/sequence.
4. Current merged contracts/specifications on authoritative `main`.
5. `docs/CURRENT_STATE.md` for implemented facts.
6. Historical handoff/audit documents for evidence only.

A planning document does not become implemented fact merely because it exists in the repository.

## 3. Authoritative branch

Project authority is `main`.

At the time this protocol was created, GitHub repository settings still list `l1/evidence-synthesis` as the default branch. That setting is stale and must not be used to select a development base. The repository owner should switch the GitHub default branch to `main` and enable protection/required CI on `main`.

Until the setting is repaired, every developer must specify `main` explicitly when reading/branching.

## 4. Work lifecycle

```text
Observation / external review
        ↓
WEB-CONTROL decision
        ↓
GitHub Issue: objective + scope + out-of-scope + executor + Gate
        ↓
branch from current main
        ↓
WEB-DEV or LOCAL-DEV implementation
        ↓
self-check + exact-head evidence
        ↓
PR
        ↓
CI + required local Gate
        ↓
WEB-CONTROL exact-head review
        ↓
MERGE_APPROVED <sha>
        ↓
merge
        ↓
update CURRENT_STATE / close Issue
```

This lifecycle is a control model, not a requirement to stop at every arrow. For low-risk in-scope work, executors should collapse multiple steps into one execution pass and return a consolidated evidence package.

Discovery that changes architecture, schema, contract, benchmark semantics, gold data or irreversible data operations returns to WEB-CONTROL before implementation continues. Minor reversible implementation details do not require a new control cycle.

## 5. Gate classes

### G0 — governance/docs
- changed files match declared scope;
- links/branch facts are current;
- no accidental functional code changes.

### G1 — deterministic code
- targeted unit/contract tests;
- relevant regression suite;
- hosted Research OS CI green on exact head.

### G2 — local integration
Required in addition to G1 when touching Qdrant, models/ROCm, local corpus/index lifecycle, external Worker lifecycle or Cognition integration.
Evidence must record environment, command, exact head and observed result.

### G3 — retrieval/benchmark
Required in addition to G1/G2 for retrieval/ranking/chunking/corpus-routing changes:
- frozen benchmark identity;
- before/after metrics;
- per-query failure analysis;
- latency impact;
- no gold mutation;
- Development vs Holdout separation.

**Gate selection rule:** apply the minimum Gate class that covers the changed risk surface. Do not require G2/G3 evidence for changes that do not touch those boundaries.

## 6. Current program assessment

### Stable foundation
The repository already has a substantial Evidence/Retrieval/TaskPack/Validation/Research-OS foundation and a lightweight CI path. This is no longer an initialization-stage codebase.

### Current control risks
1. GitHub default branch still points to `l1/evidence-synthesis` rather than `main`.
2. Two functional PRs (#24 and #28) predate this control model and need explicit triage.
3. Historical handoff documents mix old and new stages; executors must not infer authority from file age/name alone.
4. P8 Legacy Golden 50 is structurally concentrated in flagship documents, so flagship isolation is evidence of distractor competition, not sufficient proof of production routing architecture.
5. Full-corpus index/reconcile nondeterminism is an engineering blocker for trustworthy benchmark iteration.

## 7. Current priority order

### P0 — control and determinism
- repair repository branch governance;
- triage #24/#28 under exact-head Gate;
- reproduce and fix/contain index reconcile nondeterminism.

### P1 — benchmark validity
- keep Legacy 50 immutable as canary;
- build mixed-corpus Development and Holdout sets using local corpus;
- freeze schemas, provenance and split rules.

### P1 — corpus quality experiment
- run representative shadow re-extraction/metadata-repair experiment on affected foreign-research subset;
- no full-corpus destructive rewrite until evidence supports it.

### P2 — routing experiment
Only after mixed benchmark and metadata shadow evidence:
- implement/evaluate non-oracle query-time Corpus Routing;
- report router accuracy, oracle upper bound, retrieval quality and latency;
- production routing remains unapproved until Holdout evidence passes.

### P3 — larger reranker
Only after upstream candidate/corpus effects are controlled. Compare 0.6B vs larger reranker on identical candidate lists.

## 8. Existing PR policy

### PR #24 — DL-06C
Blocked. Must reconcile the preflight/formal-preview contract and obtain fresh exact-head hosted CI plus required LOCAL-DEV Cognition/Worker integration evidence before final review.

### PR #28 — DL-08
Feature direction is reasonable but it was opened before current governance. It must be refreshed against authoritative `main`, revalidated, and reviewed for persistence/migration/API semantics before merge. It must not leapfrog higher-priority control/determinism work without WEB-CONTROL decision.

## 9. Documentation rule

`docs/CURRENT_STATE.md` records merged implemented facts, not intentions. Planning and review documents must clearly label recommendations/experiments as such. Public repository documents must not describe the repository itself as private.
