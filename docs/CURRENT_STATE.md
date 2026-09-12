# AI-Knowledge-Engine Current State

更新日期：2026-09-12  
阶段：Research OS / Deep Learning Platform — P0 安全整改完成，DL-08A 收口中

> 本文件描述 **当前有效状态**。历史实现细节以 Git 历史、Issue / PR 和专项文档为准。  
> 2026-09-12 之前关于“Agent/窗口直接启动 Codex / Claude / Terminal External Worker”的描述已经被 P0 治理与 Issue #56 产品整改 supersede，不再是可执行授权或当前产品行为。

## 1. 权威来源与角色

权威开发分支：`main`。  
GitHub repository default branch 仍错误指向 `l1/evidence-synthesis`，由 Issue #33 跟踪 Owner Action；不得因此把 default branch 当成项目 SSOT。

推荐读取顺序：

1. `AGENTS.md`
2. `docs/PROJECT_CONTROL.md`
3. GitHub Issue #30
4. 当前 assigned Issue / PR
5. `docs/CURRENT_STATE.md`
6. `docs/HANDOFF_PROTOCOL.md`

角色边界：

- **WEB-CONTROL**：roadmap、scope、architecture / contract、Gate、exact-head review、`MERGE_APPROVED`、merge / release / formal-write authorization。
- **WEB-DEV / ONLINE-DEV**：按 Issue 实现窄 PR，不得自行 merge 或扩大架构/契约范围。
- **LOCAL-DEV-A/B**：仅执行需要本地 corpus / Qdrant / Cognition / Windows 环境的已授权验证；不得自行 merge，不得跨越 X0 外部资源边界。

## 2. 当前架构边界

```text
AI-Knowledge-Engine
= Evidence / Retrieval / TaskPack / Validation Engine
+ Research Workflow Host

Cognition App
= sole formal cognition writer

External model/service
= outside project-agent authority unless user explicitly authorizes the concrete operation
```

永久边界：

- Cognition App 是唯一正式 Cognition Writer；
- KE 不直接写正式 Cognition Markdown；
- Preview 必须零写入；
- Apply 必须显式 Human Apply；
- 不自动 Apply / promotion；
- Report 与 Cognition 的 SQLite / Qdrant scoring space 保持分离；
- `cog:<relpath>` KE identity 与 Cognition front-matter UUID 维持 dual-identity bridge；
- derived catalog hash 与 official Cognition `_hash` 分离；
- `relation_change` 仅 staging；
- `add_evidence` 必须显式 supporting / counter polarity。

## 3. P0 / X0 外部资源边界（最高优先级）

2026-09-12 事故 `INCIDENT-20260912-CODEX-01` 后，以下规则为最高优先级：

```text
EXTERNAL_ACCOUNT_USE: NO
EXTERNAL_PAID_SERVICE: NO
PRIVATE_DATA_EGRESS: NO
CODEX_INVOCATION: PROHIBITED
```

任何项目窗口 / Agent / subagent / harness / automation 均不得直接或间接：

- 调用 Codex CLI / Desktop / API / SDK / wrapper；
- 代表用户使用外部账户、已有登录态、API key 或 SaaS identity；
- 消耗用户 subscription / quota / token credits / billable API capacity；
- 将私有 corpus、Cognition、TaskPack、未公开研究材料发送到外部服务；
- 通过其它窗口或子进程绕过上述规则。

需要真实外部执行时，项目侧统一停在：

```text
USER_RUN_REQUIRED
```

只有用户本人在 Agent/窗口控制之外执行并主动提供结果，项目才能继续处理该结果。

详细事故与整改：

`docs/incidents/INCIDENT_P0_20260912_EXTERNAL_TOOL_INVOCATION_REMEDIATION.md`

## 4. External Worker 当前产品行为

Issue #56 / PR #57 已把外部执行从 Prompt 约束下沉到应用层 fail-closed。

当前有效行为：

- TaskPack 创建、查看、复制指令、导入用户提供结果、Importer Gate、rescan 均可继续使用；
- `GET /api/synthesis/worker-launchers` 返回 `execution_policy=USER_RUN_REQUIRED`、`agent_launch_allowed=false`，不广告任何可由 Agent/API 执行的 launcher；
- `POST /api/synthesis/tasks/{task_id}/launch-worker` 对 READY TaskPack 返回 HTTP 403 + `USER_RUN_REQUIRED`；
- `ExternalWorkerLauncher.launch_ready()` 在 executable/PATH 探测、TaskPack `READY -> PROCESSING`、`Popen` / detached subprocess 之前 fail closed；
- 不存在环境变量、角色或测试任务可绕过的真实外部执行后门；
- 不允许自动 external retry；
- deterministic fake / stub / recorded fixture 测试仍允许。

因此以下历史语义已经失效：

```text
Task Center -> 选择 Codex / Claude / Terminal -> 自动执行
```

当前语义是：

```text
TaskPack READY
-> 项目侧准备 / 查看 / 复制任务材料
-> USER_RUN_REQUIRED
-> 用户可在项目 Agent 控制之外自行执行外部工具（如其本人决定）
-> 用户提供 result
-> KE Importer / Validation / Return Candidate 流程继续
```

## 5. 已完成的关键里程碑

### Retrieval / P8

- deterministic document identity reconcile 已完成；
- Legacy50 / Dev20 / Holdout benchmark plumbing 已建立；
- Holdout 10/10 aggregate acceptance 完成；
- heading metadata shadow repair 结论为 `LIMITED_REPAIR`，未授权 full migration；
- corpus routing / full metadata migration 暂无依据直接推进。

### Deep Learning Platform / Research Loop

已完成并进入 `main` 的核心能力包括：

- DL-01 Cognition derived catalog / vector sync foundation；
- DL-02 Topic / Dossier；
- DL-03 Research Context Pack；
- DL-04 Increment Candidates；
- DL-05 / DL-05C Gap / Topic Card policy；
- DL-06 Return Candidate protocol；
- DL-06C verified Cognition Preview / Human-Apply adapter；
- DL-06D frontend return-review UI；
- formal Cognition lifecycle 的 synthetic / disposable sandbox 验证；
- P0 External Worker fail-closed 产品整改。

DL-06C / DL-06D 当前目标链路：

```text
result supplied to KE
-> return candidate
-> Human Review
-> KE Preflight
-> Formalize
-> official Cognition Preview
-> explicit Human Apply
-> readback
```

## 6. 当前唯一功能 Critical Path：DL-08A / Issue #50 / PR #54

目标：对 return candidate 的 **机械 provenance omission** 做 deterministic KE-side closure，不降低 provenance Gate。

约束：

- 只从 candidate 已声明、合法且可解析的 source refs 推导 evidence；
- 不新增 retrieval / embedding / fuzzy / title matching / semantic inference / model call；
- 不改 `proposed_text / reason / intent / target IDs / source refs`；
- 所有 input / derived evidence 必须属于 TaskPack membership；
- invalid ref、越界、outside-TaskPack、target-ID mismatch、malformed result 均 fail closed；
- 重复 closure / ingest 必须 deterministic + idempotent。

PR #54 原 head `4dd1d0ba104d97ff9507582d2906f4c31a037281` 已在旧 main 上通过代码审查和 hosted CI，但其旧 Gate 中的 real-Codex replay 已被 P0 撤销且相关 Agent-controlled external evidence 为 non-authoritative。

当前 Gate：

1. PR #54 先 reconcile 到当前 authoritative `main`；
2. exact-head hosted Research OS CI green；
3. DL-08A focused deterministic tests green；
4. DL-06 return / formal adapter / importer regressions green；
5. Issue #56 external-resource fail-closed tests green；
6. WEB-CONTROL exact-head review；
7. `MERGE_APPROVED <sha>` 后方可 merge。

**不需要、也不允许项目 Agent 再运行真实 Codex / Claude / external Worker replay。**

## 7. 当前 Open Governance Item

### Issue #33 — default branch / main protection

当前 repository metadata 仍显示：

```text
default_branch = l1/evidence-synthesis
```

项目 SSOT 已是 `main`。Issue #33 要求：

- 将 GitHub default branch 切换为 `main`；
- 为 `main` 配置 PR / CI / force-push protection；
- 完成后再处理历史 `l1/evidence-synthesis`。

当前连接可读取 repository metadata，但本会话可用 GitHub action 没有 repository-settings mutation，因此仍保留为 Owner Action，不伪装完成。

## 8. CI 当前要求

Hosted `Research OS CI` 是在线功能 PR 的默认 deterministic Gate，至少保持：

- Backend contracts / retrieval regressions；
- DL-06 return protocol / formal Cognition adapter；
- 当前 active Issue focused tests；
- Issue #56 external-resource security regressions；
- Frontend typecheck / build；
- Runtime PowerShell syntax。

CI 不得：

- 真实调用 Codex / Claude / 外部付费模型；
- 使用用户外部账户；
- 将私有项目数据发送给外部服务。

## 9. 当前 Formal Write 状态

未授权用户真实 Cognition root 的 production/formal cutover。

允许：

- deterministic tests；
- disposable / synthetic Cognition sandbox；
- official Preview 的零写入验证；
- 在已授权 disposable environment 中显式 Human Apply 验证；
- 对用户本人提供的外部结果做 KE-side import / validation。

不允许：

- 项目 Agent 对用户真实 Cognition root 自动 Apply；
- production write / cutover；
- 以“测试需要”为由绕开 sole-writer / Human Apply 边界。

## 10. 下一步执行顺序

当前顺序固定为：

```text
A. ONLINE-DEV refresh PR #54 onto current main
B. hosted CI + exact-head WEB-CONTROL review
C. 若 PASS：MERGE_APPROVED + merge + close Issue #50
D. 重新读取 main / development plan，创建下一窄 Issue
E. 下一阶段优先验证“单主题完整研究闭环”的 deterministic / user-supplied-result 路径，不恢复 Agent-controlled external Worker
```

在 PR #54 完成前，不再并行开启会修改同一 return-candidate / CI 契约面的功能 PR。

## 11. 永久原则

> 技术上可执行，不等于项目上有权限执行。  
> 本地 shell 权限，不等于用户外部账户、订阅额度或私有数据外发权限。  
> 项目 Gate 不得隐含外部账户授权。  
> 高影响安全边界必须尽可能下沉到不可绕过的产品控制。  
> 对当前项目，效率原则适用于低风险事项；X0、schema、formal write、merge/release 等材料边界仍必须显式控制。
