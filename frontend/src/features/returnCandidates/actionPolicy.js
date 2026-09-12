export function getReturnCandidateActionPolicy(input) {
  const accepted = input.status === 'accepted';
  const relationStagingOnly = input.intent === 'relation_change';
  const cleanPreflight = Boolean(
    input.preflight
      && input.preflight.ke_preflight_only === true
      && input.preflight.has_version_conflict !== true
      && input.preflight.version_check_incomplete !== true,
  );
  const formalized = Boolean(input.handoff);
  const previewed = Boolean(input.handoff?.preview);
  const applied = Boolean(input.handoff?.apply || input.formalWritePerformed);
  const polarityReady = input.intent !== 'add_evidence'
    || input.polarity === 'supporting'
    || input.polarity === 'counter';
  const serverConflict = Boolean(input.serverConflict);

  return {
    accepted,
    relationStagingOnly,
    cleanPreflight,
    formalized,
    previewed,
    applied,
    polarityReady,
    canFormalize: accepted
      && cleanPreflight
      && polarityReady
      && !relationStagingOnly
      && !formalized
      && !applied
      && !serverConflict,
    canPreview: accepted
      && cleanPreflight
      && !relationStagingOnly
      && formalized
      && !applied
      && !serverConflict,
    canApply: accepted
      && cleanPreflight
      && !relationStagingOnly
      && formalized
      && previewed
      && !applied
      && input.formalApplySupported === true
      && input.applyConfirmed === true
      && !serverConflict,
  };
}

export function returnCandidateDisabledReason(action, policy) {
  if (policy.applied) return '该 candidate 已完成 Human Apply，不可重复操作。';
  if (policy.relationStagingOnly) return 'relation_change 仅 staging-only；不存在通用 Relation Formal API。';
  if (!policy.accepted) return 'candidate 必须先由人工 Review 为 accepted。';
  if (!policy.cleanPreflight) return '必须先取得干净的 KE-side Preflight；stale/version conflict 会阻断 formal path。';
  if (action === 'formalize' && !policy.polarityReady) return 'add_evidence 必须显式选择 supporting 或 counter。';
  if (action === 'formalize' && policy.formalized) return '该 candidate 已经 Formalize。';
  if (action === 'preview' && !policy.formalized) return '必须先 Formalize 创建 Cognition Proposal item。';
  if (action === 'apply' && !policy.previewed) return '必须先执行 Cognition official Preview（zero-write）。';
  if (action === 'apply' && !policy.formalApplySupported) return '后端当前未启用 Formal Apply。';
  if (action === 'apply' && !policy.applyConfirmed) return '必须显式确认 Human Apply。';
  return null;
}
