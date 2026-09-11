# WEB-CONTROL Handoff

更新日期：2026-09-11  
仓库：`yjiao4903-lang/AI-Knowledge-Engine`  
控制源：Issue #30  
权威代码基线：`main`（交接开始时 `035eccccb831f18569beac5ffe5c2c0971a627a4`）

> 本文件是 2026-09-11 起的新窗口接手入口。任何后续 WEB-CONTROL / WEB-DEV / LOCAL-DEV 窗口在继续开发前，先核对 `main`、Issue #30、相关 Issue/PR 的实时状态；不要只依赖旧 `CURRENT_STATE.md` / `HANDOFF_PROTOCOL.md` 中的历史路线。

## 1. 必读顺序

1. `AGENTS.md`
2. `docs/PROJECT_CONTROL.md`
3. Issue #30 — Project Control Board
4. 本文件 `docs/WEB_CONTROL_HANDOFF.md`
5. 若执行本地任务：`docs/LOCAL_DEV_START.md`
6. 再读取被分配 Issue、目标 PR 与 exact-head CI / local evidence

## 2. 权限模型

### WEB-CONTROL
唯一负责：路线、优先级、Issue scope/owner、架构/Schema/Contract、Gate、最终 PR review、`MERGE_APPROVED <sha>`、Merge/Release/Cutover/production-write 授权。

### WEB-DEV
只执行已分配线上开发任务：分支、代码、测试、PR、exact-head evidence。不得自行扩 Scope、改架构/Schema/Contract、Merge/Release/production write。

### LOCAL-DEV
执行本地文件、真实 corpus/Qdrant/模型/ROCm/Cognition App/Worker/integration test。必须基于已分配 Issue/branch，保留无关本地改动，不得自行 Merge。

任何新窗口都不能因为 GitHub 技术权限而自动获得 WEB-CONTROL 项目权限；须以用户分配身份和 Issue #30 为准。

## 3. 当前最高优先级：P8-BENCH-02（Issue #39 / PR #41）

### 当前状态

- Issue #39：open，`needs-human-review`。
- PR #41：open，未合并。
- 分支：`local-dev/39-p8-benchmark-pilot`。
- 当前已验收 exact head：`955ecf576e79b2963070c70cf45f0aaec0574fbc`。
- Research OS CI run #272：backend / frontend / PowerShell 全绿。
- WEB-CONTROL 已明确：**correction/tooling gate PASSED，但不是 `MERGE_APPROVED`。**

### 已完成

1. 自动生成结果已降级为 `auto_prelabel`，不得作为人工相关性或检索质量证据。
2. 已实现 blinded adjudication：隐藏 retrieval view / rank / score / auto grade。
3. 已实现人工判定 schema：grade 0/1/2/3 + `accept|rewrite|reject|ambiguous` + reviewer metadata。
4. 已生成校准包：20 Development + 10 sealed Holdout。
5. `accept/rewrite` 已强制 candidate-level 100% completeness；missing / duplicate / unknown / null grade 均 fail。
6. `reject/ambiguous` 为 query-level disposition，明确排除出 gold 和全部 metric aggregate。
7. Holdout per-query 内容、judgments、key 保持仓库外密封。

### 当前唯一 Gate

必须由**真实人工领域审阅者**完成 20 Dev + 10 sealed Holdout 的 blinded review。禁止 LOCAL-DEV / 模型自动生成后冒充 `human` grades。

人工完成后，LOCAL-DEV 依次执行：

1. `import --require-complete`；
2. 只由 human grades 重建并冻结 gold；
3. 生成 auto-prelabel vs human disagreement；
4. 执行 human false-negative audit；
5. 用 human gold 重跑 retrieval metrics；
6. 返回新 exact-head SHA + CI + local evidence。

然后由 WEB-CONTROL 做最终方法学 review；只有通过后才能记录 `MERGE_APPROVED <sha>` 并合并 PR #41。

### 明确禁止

- 不得把旧 auto-prelabel Hit@5 / `no pooled grade-3` 结果解释成 benchmark validity 或 retrieval quality 结论；
- 不得提前扩到 150+150；
- 不得调 retrieval weights；
- 不得实现 Corpus Routing；
- 不得升级 reranker；
- 不得改 Legacy 50；
- 不得 corpus rewrite / reindex。

## 4. 并行工作流：PR #24 / Issue #26

Issue #26 已完成并关闭；PR #24 contract reconciliation 当前 exact head：

`0076ccb886c204bdf380599e0ef98674d324b54b`

Hosted Research OS CI 已在该 exact head 成功。KE staging `/preflight` 已恢复：

- `ke_preflight_only=true`
- `formal_preview_supported=false`
- `formal_apply_supported=false`
- `formal_write_performed=false`

但 **PR #24 仍不能合并**：还缺 LOCAL-DEV 的真实 Cognition/Worker integration smoke，以及 WEB-CONTROL 对同一 exact head 的最终 review / `MERGE_APPROVED`。

Issue #27（DL-06D UI）继续排队在 PR #24 之后，PR #24 未合并前不得启动依赖性功能 PR。

## 5. 仓库治理未完成项：Issue #33

Issue #33 仍 open：仓库 GitHub 设置中的 default branch / main protection 需要 owner/admin 操作。

项目逻辑上始终以 `main` 为权威；任何工具调用、分支、文件读取、PR base 都应显式使用 `main`，直到 Issue #33 被外部确认关闭。

Owner 需完成：

- default branch 切到 `main`；
- main 要求 PR + Research OS CI；
- 禁止 force push / deletion；
- 确认历史 `l1/evidence-synthesis` 无遗漏后再归档/删除。

## 6. 已完成的 P8 基线

- Governance PR #31 已合并。
- P8 reconcile determinism Issue #32 / PR #35 已完成并合并。
- P8-BENCH-01 Issue #36 / PR #38 已完成，但结论仅是自动 benchmark 的 limiting-factor diagnosis，不是正式 benchmark。
- Legacy 50 继续冻结为 canary。

## 7. P8 后续路线（顺序不得颠倒）

1. 完成 Issue #39 的真实 human calibration 并决定是否接受 60+40 pilot；
2. 只有 pilot 通过，WEB-CONTROL 才可新建 follow-up Issue 授权扩到 150 Dev + 150 sealed Holdout；
3. metadata-repair shadow experiment；
4. non-oracle Corpus Routing experiment；
5. routing architecture 决策；
6. 在相同 candidate lists 上比较 reranker（例如 0.6B vs 4B）。

完整 destructive corpus rewrite 始终未授权。

## 8. 永久系统边界

- Cognition App = 唯一正式 cognition writer。
- Knowledge Engine = Evidence / Retrieval / TaskPack host + staging client。
- 禁止 KE 直接写 Cognition Markdown。
- Cognition Preview / Apply / Merge / Revision / Topic Update 不得被 KE staging endpoint 冒充或隐式执行。
- production writes、Cognition Apply、full corpus rewrite/re-extraction/rechunk/reindex、destructive migration、gold mutation、release/cutover 均需 WEB-CONTROL 单独显式授权。

## 9. 新窗口启动模板

### 新 WEB-CONTROL

> 读取 `AI-Knowledge-Engine` 的 `main`：`AGENTS.md`、`docs/PROJECT_CONTROL.md`、`docs/WEB_CONTROL_HANDOFF.md`，再核对 Issue #30、#39、#33、PR #41、PR #24 的实时状态。先恢复控制面，不要直接开发或合并；所有决策基于最新 exact head / CI / local evidence。

### LOCAL-DEV

> 请重新读取 `AI-Knowledge-Engine` 仓库 `main` 分支的 `docs/LOCAL_DEV_START.md`，再读取 `docs/WEB_CONTROL_HANDOFF.md` 和当前分配 Issue 的最新评论，严格按当前 Gate 执行。

### WEB-DEV

> 读取 `main` 的 `AGENTS.md`、`docs/PROJECT_CONTROL.md`、`docs/WEB_CONTROL_HANDOFF.md`，只执行 WEB-CONTROL 明确分配的 open Issue；不要从历史 PR/README 自行推导新 Scope。

## 10. 交接原则

如果本文件与更晚的 Issue #30 WEB-CONTROL 评论、目标 Issue/PR exact-head review 冲突，以**时间更晚、范围更具体、且来自 WEB-CONTROL 的 GitHub 记录**为准。接手窗口必须先重新读取 GitHub 当前事实，不能把本文件中的 SHA 当成永远不变的事实。
