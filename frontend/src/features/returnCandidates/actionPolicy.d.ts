export interface ReturnCandidatePolicyInput {
  status: string;
  intent: string;
  preflight: {
    ke_preflight_only?: boolean;
    has_version_conflict?: boolean;
    version_check_incomplete?: boolean;
  } | null;
  handoff: { preview?: unknown; apply?: unknown } | null;
  polarity: 'supporting' | 'counter' | null;
  formalApplySupported: boolean;
  formalWritePerformed: boolean;
  serverConflict: boolean;
  applyConfirmed: boolean;
}

export interface ReturnCandidateActionPolicy {
  accepted: boolean;
  relationStagingOnly: boolean;
  cleanPreflight: boolean;
  formalized: boolean;
  previewed: boolean;
  applied: boolean;
  polarityReady: boolean;
  canFormalize: boolean;
  canPreview: boolean;
  canApply: boolean;
}

export function getReturnCandidateActionPolicy(input: ReturnCandidatePolicyInput): ReturnCandidateActionPolicy;
export function returnCandidateDisabledReason(
  action: 'formalize' | 'preview' | 'apply',
  policy: ReturnCandidateActionPolicy,
): string | null;
