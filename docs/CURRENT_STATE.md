# AI-Knowledge-Engine Current State

更新日期：2026-09-12  
阶段：Research OS / Deep Learning Platform — P0/X0 安全整改完成，DL-07R 权威 E2E 复验进行中

> 本文件只描述 **当前有效状态**。历史实现细节以 Git 历史、Issue / PR 和专项文档为准。  
> 2026-09-12 之前关于“Agent/窗口直接启动 Codex / Claude / Terminal External Worker”的描述已被 P0 治理与 Issue #56 产品整改 supersede，不再构成当前产品行为或执行授权。

## 1. 权威来源与角色

项目权威开发分支：`main`。  
GitHub repository default branch 仍错误指向 `l1/evidence-synthesis`，由 Issue #33 跟踪 Owner Action；不得把 repository default branch 当成项目 SSOT。

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

永久约束：

- Cognition App 是唯一正式 Cognition Writer；
- KE 不直接写正式 Cognition Markdown；
- Preview 必须零写入；
- Apply 必须显式 Human Apply；
- 不自动 Apply / promotion；
- Report 与 Cognition 的 SQLite / Qdrant scoring space 保持分离；
- KE `cog:<relpath>` identity 与 Cognition front-matter UUID 维持 dual-identity bridge；
- derived catalog hash 与 official Cognition `_hash` 分离；
- `relation_change` 仅 staging；
- `add_evidence` 必须显式 supporting / counter polarity。

## 3. P0 / X0 外部资源边界

2026-09-12 事故 `INCIDENT-20260912-CODEX-01` 后，以下为最高优先级默认值：

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
- 通过其它窗口、脚本或子进程绕过上述规则。

需要真实外部执行时，项目侧统一停在：

```text
USER_RUN_REQUIRED
```

详细事故与整改：

`docs/incidents/INCIDENT_P0_20260912_EXTERNAL_TOOL_INVOCATION_REMEDIATION.md`

## 4. External Worker 当前产品行为

Issue #56 / PR #57 已把外部执行从 Prompt 约束下沉为应用层 fail-closed。

当前有效行为：

- TaskPack 创建、查看、复制指令、导入用户提供结果、Importer Gate、rescan 可继续使用；
- `GET /api/synthesis/worker-launchers` 返回 `execution_policy=USER_RUN_REQUIRED`、`agent_launch_allowed=false`；
- `POST /api/synthesis/tasks/{task_id}/launch-worker` 对 READY TaskPack 返回 HTTP 403 + `USER_RUN_REQUIRED`；
- `ExternalWorkerLauncher.launch_ready()` 在 PATH/executable 探测、TaskPack `READY -> PROCESSING`、`Popen` / detached subprocess 前 fail closed；
- 不允许自动 external retry；
- deterministic fake / stub / recorded fixture 测试允许。

当前研究回流路径是：

```text
TaskPack READY
-> 项目侧准备 / 查看 / 复制任务材料
-> USER_RUN_REQUIRED（如需真实外部模型）
-> 用户可在 Agent 控制之外自行提供结果
   或技术验收使用完全本地 deterministic worker-boundary fixture
-> KE Importer / Validation / Return Candidate
-> Human Review
-> KE Preflight
-> Formalize
-> official Cognition Preview
-> explicit Human Apply
-> readback
```

## 5. 已完成关键里程碑

### Retrieval / P8

- deterministic document identity reconcile 已完成；
- Legacy50 / Dev20 / Holdout benchmark plumbing 已建立；
- Holdout aggregate 10/10 acceptance 已完成；
- heading metadata shadow repair 结论为 `LIMITED_REPAIR`，未授权 full migration；
- corpus routing / full metadata migration 暂无依据直接推进。

### Deep Learning Platform / Research Loop

当前已进入 `main` 的核心能力：

- DL-01 Cognition derived catalog / vector sync foundation；
- DL-02 Topic / Dossier；
- DL-03 Research Context Pack；
- DL-04 Increment Candidates；
- DL-05 / DL-05C Gap / Topic Card policy；
- DL-06 Return Candidate protocol；
- DL-06C verified Cognition Preview / Human-Apply adapter；
- DL-06D frontend return-review UI；
- formal Cognition lifecycle 的 disposable/synthetic sandbox 验证；
- DL-08A deterministic provenance closure；
- P0 External Worker fail-closed 产品整改。

### DL-08A / Issue #50 / PR #54 — DONE

目标：机械修复 return candidate 自己已声明 source refs 所确定的 provenance omission，不降低 provenance Gate。

最终证据：

- approved exact head：`e7eb67aa941477fc50d9eccd8a52e3c903ad45a8`；
- Research OS CI #315 / run `34695019389`：Backend / Frontend / PowerShell 全绿；
- merge commit：`d7ce5c77ebd5fb1c65c1f9fe80541a901577bc9d`；
- Issue #50：closed / completed；
- Issue #56 external-resource fail-closed tests 与 DL-08A / importer / DL-06 regressions在同一 exact-head CI 中通过。

旧 real-Codex replay requirement 已永久撤销，相关 Agent-controlled external evidence 为 non-authoritative。

## 6. 当前唯一功能 Critical Path：DL-07R / Issue #58

Issue #58：`[LOCAL-DEV-A] DL-07R — authoritative single-topic E2E reacceptance without external Worker execution`

原因：原 DL-07 曾包含未授权的 Agent-controlled real Codex execution，因此那部分外部运行证据不能继续作为项目权威 E2E Gate。DL-08 依赖 DL-07，所以在推进知识复用功能前，先恢复一份不依赖外部 Agent 调用的单主题技术闭环证据。

### 当前技术验收流

```text
Topic / Dossier
-> Research Context Pack / selected Cognition snapshot
-> TaskPack READY
-> inject deterministic local SynthesisDraftV1 / ResultEnvelope fixture
-> Importer Gate
-> Return Candidate ingest
-> DL-08A deterministic provenance closure
-> Human Review
-> KE Preflight
-> Formalize
-> official Cognition Preview
-> explicit Human Apply（仅 disposable synthetic Cognition root）
-> official readback
-> verify updated object linkage / next research-cycle state
```

### 必须证明

- fixture 完全本地、deterministic，不调用任何外部模型/服务；
- DL-08A 只补 candidate 自己合法 source refs 唯一决定的 in-TaskPack evidence；
- semantic fields 不被 closure 改写；
- KE `cog:<relpath>` 与 formal UUID 双身份正确；
- catalog hash 与 official `_hash` 分离；
- Preview 零写入；
- Apply 仅在 disposable environment 中显式确认后发生；
- Apply 后 official readback 正确；
- stale-after-preview / duplicate Apply / malformed UUID / target typo / outside-TaskPack evidence / invalid source ref / relation_change / missing polarity 均继续 fail closed；
- Issue #56 launch endpoint 继续 403 / `USER_RUN_REQUIRED`；
- 用户真实 Cognition root 零写入。

### 结果分类

- `TECHNICAL_PASS`：上述本地 deterministic 单主题闭环全部通过；
- `HUMAN_REVIEW_PENDING`：技术通过不等于用户已确认研究价值或模型质量；
- 若发现产品缺陷：Issue #58 停在失败边界，转给 ONLINE-DEV 新建窄 defect Issue；不得在 LOCAL-DEV Issue 中扩架构/契约。

Issue #58 不授权 production/formal-user cutover。

## 7. DL-08 / DL-09 状态

根据 `docs/DEEP_LEARNING_PLATFORM_DEVELOPMENT_PLAN.md`：

- DL-08：知识复用与理解记录，依赖 DL-07；
- DL-09：多主题发现与渐进扩展，依赖 DL-07 和真实反馈。

因此当前：

```text
DL-08 = BLOCKED_BY_DL07R_TECHNICAL_ACCEPTANCE
DL-09 = BLOCKED_BY_DL07R + HUMAN_FEEDBACK
```

Issue #58 `TECHNICAL_PASS` 前，不开启会修改同一研究闭环面的 DL-08 功能 PR。

## 8. Open Governance Item：Issue #33

repository metadata 仍显示：

```text
default_branch = l1/evidence-synthesis
```

项目 SSOT 已是 `main`。Issue #33 要求：

- GitHub default branch 切换为 `main`；
- `main` 配置 PR / CI / force-push protection；
- 完成后再处理历史 `l1/evidence-synthesis`。

当前会话可用 GitHub action 没有 repository-settings mutation，因此继续保持 Owner Action，不伪装完成。

## 9. CI 当前要求

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

## 10. Formal Write 状态

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
- 以“测试需要”为由绕过 sole-writer / Human Apply 边界。

## 11. 当前执行顺序

```text
A. LOCAL-DEV-A 执行 Issue #58 单一 integrated E2E Gate
B. 若无代码缺陷：WEB-CONTROL 审核证据并登记 TECHNICAL_PASS
C. 若有代码缺陷：建立窄 ONLINE-DEV defect Issue -> PR -> CI -> exact-head review
D. TECHNICAL_PASS 后进行用户 Human Review checkpoint
E. 再决定是否启动 DL-08 知识复用与理解记录
```

LOCAL-DEV-B 暂待命，仅在 Issue #58 暴露需要独立 Cognition/fault 复核的问题时启用。  
ONLINE-DEV 暂停新功能，除非 Issue #58 产生明确代码 defect。

## 12. 永久原则

> 技术上可执行，不等于项目上有权限执行。  
> 本地 shell 权限，不等于用户外部账户、订阅额度或私有数据外发权限。  
> 项目 Gate 不得隐含外部账户授权。  
> 高影响安全边界必须尽可能下沉到不可绕过的产品控制。  
> 效率原则适用于低风险事项；X0、schema、formal write、merge/release 等材料边界仍必须显式控制。
