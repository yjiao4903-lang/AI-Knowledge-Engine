export type TopicCandidateStatus = 'proposed' | 'accepted' | 'rejected' | 'deferred';

export type TopicCandidateSourceType =
  | 'open_question'
  | 'additional_evidence_needed'
  | 'potential_conflict'
  | 'cannot_determine'
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
  formal_write_performed: false;
};

export type TopicCandidateRefreshResponse = {
  refresh: {
    dossier_id: string;
    discovered: number;
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
