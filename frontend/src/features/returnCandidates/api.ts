export type ReturnIntent =
  | 'new_judgment'
  | 'add_evidence'
  | 'revise_judgment'
  | 'suggest_retract'
  | 'advance_question'
  | 'relation_change';

export type ReturnReviewStatus = 'proposed' | 'accepted' | 'rejected' | 'deferred';
export type EvidenceRole = 'supporting' | 'counter';
export type TargetVersionState = 'unchanged' | 'changed' | 'missing' | 'unavailable' | 'unknown_baseline';

export interface ReturnTargetSnapshot {
  object_id: string;
  object_type: string;
  baseline_content_hash: string | null;
  baseline_title: string | null;
  baseline_excerpt: string | null;
  current_content_hash: string | null;
  current_title: string | null;
  current_excerpt: string | null;
  version_state: TargetVersionState;
  checked_at: string;
}

export interface ReturnCandidateRecord {
  schema_version: string;
  candidate_id: string;
  task_id: string;
  task_query: string;
  result_generated_at: string;
  intent: ReturnIntent;
  target_cognition_object_ids: string[];
  proposed_text: string;
  reason: string;
  evidence_chunk_ids: string[];
  source_claim_ids: string[];
  source_tension_ids: string[];
  source_open_question_indexes: number[];
  source_additional_evidence_indexes: number[];
  proposer: string;
  target_snapshots: ReturnTargetSnapshot[];
  has_version_conflict: boolean;
  version_check_incomplete: boolean;
  status: ReturnReviewStatus;
  review_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  formal_preview_supported: false;
  formal_apply_supported: false;
  formal_write_performed: false;
}

export interface ReturnCandidateBatch {
  schema_version: string;
  task_id: string;
  updated_at: string;
  candidates: ReturnCandidateRecord[];
  formal_write_performed: false;
}

export interface ReturnCandidateBatchResponse {
  return_candidates: ReturnCandidateBatch;
  count?: number;
  created?: number;
  reused?: number;
  source_candidates?: number;
  source?: string;
  formal_preview_supported: false;
  formal_apply_supported: false;
  auto_apply: false;
  formal_write_performed: false;
}

export interface ReturnPreflightTarget {
  object_id: string;
  object_type: string;
  baseline: { content_hash: string | null; title: string | null; excerpt: string | null };
  current: { content_hash: string | null; title: string | null; excerpt: string | null };
  version_state: TargetVersionState;
  checked_at: string;
}

export interface ReturnCandidatePreflight {
  task_id: string;
  candidate_id: string;
  intent: ReturnIntent;
  status: ReturnReviewStatus;
  proposed_text: string;
  reason: string;
  evidence_chunk_ids: string[];
  targets: ReturnPreflightTarget[];
  has_version_conflict: boolean;
  version_check_incomplete: boolean;
  ke_preflight_only: true;
  formal_preview_supported: false;
  formal_apply_supported: false;
  auto_apply: false;
  formal_write_performed: false;
}

export interface FormalTargetIdentity {
  ke_target_id: string;
  cognition_target_id: string;
  object_type: string;
  source_path: string;
}

export interface FormalPreviewMarker {
  previewed_at?: string;
  target_hashes?: Record<string, string | null>;
  response?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface FormalApplyMarker {
  applied_at?: string;
  response?: Record<string, unknown>;
  readback?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface FormalHandoffMarker {
  schema_version: string;
  task_id: string;
  candidate_id: string;
  intent: ReturnIntent;
  evidence_role: EvidenceRole | null;
  proposal_id: string;
  proposal_item_id: string;
  target_identities?: FormalTargetIdentity[];
  published_at: string;
  published_target_hashes: Record<string, string | null>;
  preview: FormalPreviewMarker | null;
  apply: FormalApplyMarker | null;
  writer: 'cognition_app';
  formal_write_performed: boolean;
}

export interface FormalHandoffResponse {
  task_id: string;
  candidate_id: string;
  formal_handoff: FormalHandoffMarker | null;
  formal_preview_supported?: boolean;
  formal_apply_supported: boolean;
  auto_apply: false;
  formal_write_performed: boolean;
  reused?: boolean;
  writer?: 'cognition_app';
}

export class ReturnCandidateApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ReturnCandidateApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new ReturnCandidateApiError(0, `无法连接后端 API：${String(error)}`);
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    const record = body && typeof body === 'object' ? body as Record<string, unknown> : {};
    const detail = record.detail;
    const message =
      (record.message as string | undefined)
      ?? (typeof detail === 'string' ? detail : undefined)
      ?? (detail !== undefined ? JSON.stringify(detail) : undefined)
      ?? response.statusText
      ?? `HTTP ${response.status}`;
    throw new ReturnCandidateApiError(response.status, message, detail);
  }
  return body as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function base(taskId: string): string {
  return `/api/research-os/tasks/${encodeURIComponent(taskId)}/return-candidates`;
}

function candidatePath(taskId: string, candidateId: string): string {
  return `${base(taskId)}/${encodeURIComponent(candidateId)}`;
}

export const returnCandidateApi = {
  ingestResult: (taskId: string) => post<ReturnCandidateBatchResponse>(`${base(taskId)}/ingest-result`),
  list: (taskId: string) => request<ReturnCandidateBatchResponse>(base(taskId)),
  refreshTargets: (taskId: string) => post<ReturnCandidateBatchResponse>(`${base(taskId)}/refresh-targets`),
  preflight: (taskId: string, candidateId: string) =>
    request<ReturnCandidatePreflight>(`${candidatePath(taskId, candidateId)}/preflight`),
  review: (taskId: string, candidateId: string, status: ReturnReviewStatus, reason?: string) =>
    post<ReturnCandidateBatchResponse>(`${candidatePath(taskId, candidateId)}/review`, {
      status,
      reason,
      reviewer: 'user',
    }),
  formalHandoff: (taskId: string, candidateId: string) =>
    request<FormalHandoffResponse>(`${candidatePath(taskId, candidateId)}/formal-handoff`),
  formalize: (taskId: string, candidateId: string, evidenceRole: EvidenceRole | null) =>
    post<FormalHandoffResponse>(
      `${candidatePath(taskId, candidateId)}/formalize`,
      evidenceRole ? { evidence_role: evidenceRole } : {},
    ),
  preview: (taskId: string, candidateId: string) =>
    post<FormalHandoffResponse>(`${candidatePath(taskId, candidateId)}/formal-preview`),
  apply: (taskId: string, candidateId: string) =>
    post<FormalHandoffResponse>(`${candidatePath(taskId, candidateId)}/formal-apply`, { confirm: true }),
};
