import type {
  CognitionContextInput,
  EvidenceContextMode,
  EvidenceRefInput,
  TaskStatus,
  TaskType,
} from './types';

export type TopicCandidateStatus = 'proposed' | 'accepted' | 'rejected' | 'deferred';

export type TopicCandidateSourceType =
  | 'open_question'
  | 'additional_evidence_needed'
  | 'potential_conflict'
  | 'cannot_determine'
  | 'condition_change'
  | 'mechanism_gap'
  | 'analogy_extension'
  | 'missing_source'
  | 'changed_source';

export type TopicCardCandidate = {
  schema_version: string;
  candidate_id: string;
  dossier_id: string;
  source_type: TopicCandidateSourceType;
  title: string;
  research_question: string;
  why_now: string;
  expected_research_value: string;
  required_evidence: string[];
  related_refs: string[];
  known: string[];
  unknown: string[];
  competing_explanations: string[];
  exploratory: boolean;
  discriminating_evidence: string[];
  evidence_availability: 'available' | 'partial' | 'unknown' | 'blocked';
  evidence_availability_reason: string;
  research_scope: string[];
  research_exclusions: string[];
  suggested_method: string;
  deliverable: string;
  duplicate_check: 'no_exact_duplicate' | 'possible_duplicate';
  duplicate_reason: string;
  possible_duplicate_refs: string[];
  workload_band: 'low' | 'medium' | 'high';
  workload_reason: string;
  priority: 'high' | 'medium' | 'low';
  priority_reason: string;
  mainline_relevance: string;
  source_task_id?: string | null;
  source_analysis_id?: string | null;
  source_candidate_id?: string | null;
  source_ref?: string | null;
  source_fingerprint: string;
  status: TopicCandidateStatus;
  review_reason?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at: string;
  formal_write_performed: false;
};

export type TopicCandidateListResponse = {
  candidates: TopicCardCandidate[];
  count: number;
  max_candidates: number;
  formal_write_performed: false;
};

export type TopicCandidateRefreshResponse = {
  refresh: {
    dossier_id: string;
    discovered: number;
    signals_discovered: number;
    selected: number;
    max_candidates: number;
    omitted_by_limit: number;
    rejected_suppressed: number;
    created: number;
    reused: number;
    invalid_task_ids: string[];
    candidate_ids: string[];
    formal_write_performed: false;
  };
  auto_create_topic: false;
  auto_apply: false;
  formal_write_performed: false;
};

export type TopicCandidateReviewResponse = {
  candidate: TopicCardCandidate;
  selected_for_research: boolean;
  auto_create_topic: false;
  auto_apply: false;
  formal_write_performed: false;
};

export type CandidateTaskRequest = {
  task_type: TaskType;
  evidence_refs: EvidenceRefInput[];
  evidence_context_mode?: EvidenceContextMode;
  cognition_object_ids?: string[];
  cognition_context?: CognitionContextInput[];
};

export type CandidateTaskResponse = {
  task_id: string;
  status: TaskStatus;
  task_path: string;
  dossier_id: string;
  topic_candidate_id: string;
  query: string;
  research_context_included?: boolean;
  cognition_context_count?: number;
  reused: boolean;
  worker_launched: false;
  auto_apply: false;
  formal_write_performed: false;
};
