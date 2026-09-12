# AI-Knowledge-Engine Project Control

Effective: 2026-09-11  
Controller: `WEB-CONTROL`  
Online board: GitHub Issue #30

## -1. P0 execution prohibition — no agent/window may invoke Codex

Effective 2026-09-12 by explicit user instruction. Incident record: Issue #55.

This rule is part of the project's highest governance layer and has priority over every later section of this document, every Issue/PR/test plan, historical handoff, efficiency rule, and any prior WEB-CONTROL authorization.

No project execution window/agent may invoke Codex directly or indirectly. This includes WEB-CONTROL, WEB-DEV/ONLINE-DEV, LOCAL-DEV-A/B, any ChatGPT project window, subagent, automation, harness, script or subprocess controlled by those executors.

Forbidden: `codex.exe`, Codex CLI, scripted/remote Codex desktop control, shell/Python/Node subprocess invocation, API/SDK/job wrappers, agent-controlled use of Codex as External Worker, delegation to another window/agent/tool, or nested Codex/subagent execution for validation.

There is no role-level exception. WEB-CONTROL cannot waive this rule. If real Codex execution is required, the executor must return `USER_RUN_REQUIRED`. Only the user may manually execute Codex outside agent/window control and provide the resulting artifacts back to the project. Changing this rule requires a new explicit user governance instruction.

Deterministic fakes/stubs/mocks, recorded fixtures and user-supplied existing artifacts remain allowed. Agent/window-controlled Codex evidence is non-authoritative for Gates. Any violation is P0 and must be stopped, recorded minimally and reported without killing unrelated user-owned Codex/Desktop processes.

## -0.5. P0 external identity / spend / data-egress control

Effective 2026-09-12. Follow-up hardening: Issue #56.

For every non-Codex external resource, project execution defaults to **DENY**. WEB-CONTROL authority over architecture/Gates does not by itself authorize use of the user's external identities, paid resources, subscriptions, credits or private-data egress.

An executor must return `USER_RUN_REQUIRED` unless the user has explicitly authorized the exact current external action when it would:
- use a user-bound external login, account, credential, API key, SaaS identity or subscription;
- consume quota, credits, billable API/service capacity or subscription capacity;
- transmit non-public corpus, Cognition, TaskPack, unpublished research or other private project/user data to an external service;
- create an externally visible side effect on a user account or remote service.

Technical capability, local shell access, an installed/logged-in client, prior usage, an Issue/PR instruction, a test requirement, or WEB-CONTROL approval is not user consent.

If the user explicitly authorizes a non-Codex external service, the task must state the authorized provider/purpose, private-data-egress permission, maximum run/retry count, and any applicable quota/cost boundary. Missing fields mean `NO / NOT AUTHORIZED`. Automatic external retries are prohibited unless explicitly and boundedly authorized by the user.

Codex remains absolutely prohibited for project windows/agents under Section -1 even if a general external-service authorization exists.

## 0. Execution-efficiency rule

Project control must optimize for **decision quality per unit of human attention**, not procedural volume.

Default behavior:
- use the lightest governance/Gate that matches the actual risk and reversibility;
- low-risk reversible details stay with the assigned executor and should be completed without repeated WEB-CONTROL round-trips;
- batch related checks, fixes, reviews and evidence into one pass;
- reuse still-valid evidence instead of repeating work for formality;
- do not apply major-project ceremony to small implementation/documentation/test details;
- escalate only for material scope expansion, architecture/schema/public-contract/benchmark-semantic changes, durable or sealed data mutation, production/formal writes, external-account/spend/data-egress boundaries, or merge/release/cutover authorization.

A process that is technically correct but repeatedly consumes human review for trivial reversible details is considered inefficient and should be simplified. Safety boundaries in Sections -1/-0.5 are never “trivial reversible details.”

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
2. `AGENTS.md` role and permission boundaries, including the P0 Codex and external-resource prohibitions.
3. GitHub Issue #30 and the assigned work Issue for scope/sequence.
4. Current merged contracts/specifications on authoritative `main`.
5. `docs/CURRENT_STATE.md` for implemented facts.
6. Historical handoff/audit documents for evidence only.

A planning document does not become implemented fact merely because it exists in the repository.

## 3. Authoritative branch

Project authority is `main`.

At the time this protocol was created, GitHub repository settings still list `l1/evidence-synthesis` as the default branch. That setting is stale and must not be used to select a development base. The repository owner should switch the GitHub default branch to `main` and enable protection/required CI on `main`.

Until the setting is repaired, every developer must specify `main` explicitly when reading/branching and every governance write must explicitly target `main`.

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

Discovery that changes architecture, schema, contract, benchmark semantics, gold data or irreversible data operations returns to WEB-CONTROL before implementation continues. Crossing external identity/spend/private-data-egress boundaries returns to the user as `USER_RUN_REQUIRED`, not merely to WEB-CONTROL. Minor reversible implementation details do not require a new control cycle.

Every new task defaults to:

```text
EXTERNAL_ACCOUNT_USE: NO
EXTERNAL_PAID_SERVICE: NO
PRIVATE_DATA_EGRESS: NO
CODEX_INVOCATION: PROHIBITED
```

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

**P0 override:** G2 never authorizes an executor to launch Codex or another unauthorized external identity-bound/paid worker. If a requested check requires such an external run, the Gate status is `USER_RUN_REQUIRED` until the user performs or explicitly authorizes the permitted action. Deterministic worker fakes/stubs and user-supplied artifacts may be used for executor-controlled validation.

### G3 — retrieval/benchmark
Required in addition to G1/G2 for retrieval/ranking/chunking/corpus-routing changes:
- frozen benchmark identity;
- before/after metrics;
- per-query failure analysis;
- latency impact;
- no gold mutation;
- Development vs Holdout separation.

### X0 — external identity / spend / data-egress authorization
X0 is orthogonal to G0-G3. A higher technical Gate never grants X0 permission. If an operation crosses Section -0.5 and lacks explicit current user authorization, status is `USER_RUN_REQUIRED` and execution stops.

**Gate selection rule:** apply the minimum technical Gate class that covers the changed risk surface, plus X0 whenever applicable. Do not require G2/G3 evidence for changes that do not touch those boundaries.

## 6. Current program assessment

### Stable foundation
The repository already has a substantial Evidence/Retrieval/TaskPack/Validation/Research-OS foundation and a lightweight CI path. This is no longer an initialization-stage codebase.

### Current control risks
1. GitHub default branch still points to `l1/evidence-synthesis` rather than `main`.
2. Historical handoff documents mix old and new stages; executors must not infer authority from file age/name alone.
3. P8 Legacy Golden 50 is structurally concentrated in flagship documents, so flagship isolation is evidence of distractor competition, not sufficient proof of production routing architecture.
4. Full-corpus index/reconcile nondeterminism is an engineering blocker for trustworthy benchmark iteration.
5. Agent/window invocation of Codex is a P0-prohibited operation; old real-Worker instructions must not be executed by project windows.
6. External identity-bound/paid-service use and private-data egress require X0 user authorization; old task wording cannot substitute for it.
7. External Worker execution needs product-level fail-closed hardening under Issue #56.

## 7. Current priority order

### P0 — safety, control and determinism
- enforce Issue #55 / `AGENTS.md` Codex invocation prohibition;
- implement Issue #56 product-level external-worker fail-closed hardening;
- preserve external identity/spend/data-egress X0 boundary;
- repair repository branch governance;
- reproduce and fix/contain index reconcile nondeterminism without prohibited external execution.

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

Historical PR notes are retained as context only; current live Issues/PRs and `main` must be re-read before action.

Any PR/Gate requesting executor-controlled real Codex execution is automatically superseded by the P0 policy and becomes `USER_RUN_REQUIRED` for that portion. Any PR/Gate requiring another external paid/account-bound service must separately satisfy X0.

## 9. Documentation rule

`docs/CURRENT_STATE.md` records merged implemented facts, not intentions. Planning and review documents must clearly label recommendations/experiments as such. Public repository documents must not describe the repository itself as private.
