// API 响应类型（依据真实后端契约建模）。

export type SearchMode = 'hybrid' | 'dense' | 'lexical';

export interface SearchFilters {
  document_ids?: string[];
  evidence_levels?: number[];
  content_types?: string[];
}

export interface SearchOptions {
  mode?: SearchMode;
  rerank?: boolean;
  top_k?: number;
  debug?: boolean;
}

export interface SearchRequest {
  query: string;
  filters?: SearchFilters;
  options?: SearchOptions;
}

export type RetrievalFeedbackEventType =
  | 'impression'
  | 'useful'
  | 'evidence_select'
  | 'evidence_remove';

export interface RetrievalFeedbackEvent {
  search_id: string;
  query: string;
  chunk_id: string;
  document_id?: string | null;
  rank: number;
  mode: SearchMode;
  rerank: boolean;
  event_type: RetrievalFeedbackEventType;
  useful: boolean | null;
  selected_as_evidence: boolean | null;
}

export interface RetrievalFeedbackBatch {
  events: RetrievalFeedbackEvent[];
}

export interface RetrievalFeedbackResponse {
  recorded: number;
  schema_version: string;
}

export interface ResultScores {
  dense_rank: number | null;
  terms_rank: number | null;
  trigram_rank: number | null;
  rrf: number | null;
  section_boost: number | null;
  final: number | null;
  reranker: number | null;
  pre_rerank_rank: number | null;
}

export interface SearchResult {
  rank: number;
  chunk_id: string;
  document_id: string;
  title: string;
  section_id: string;
  heading_path: string;
  content_type: string;
  evidence_level: number | null;
  snippet: string;
  start_line: number;
  end_line: number;
  scores: ResultScores;
  search_id?: string;
  search_mode?: SearchMode;
  rerank_enabled?: boolean;
}

export interface SearchTiming {
  embed_ms: number;
  dense_ms: number;
  terms_ms: number;
  trigram_ms: number;
  fusion_ms: number;
  section_ms: number;
  rerank_ms: number;
  filter_ms: number;
  total_ms: number;
}

export interface DebugInfo {
  sources: { dense: unknown[]; terms: unknown[]; trigram: unknown[] };
  boosted_sections: unknown[];
  candidates_before_filter: number;
  fused_top: unknown[];
  rerank: unknown[];
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  search_id?: string;
  results: SearchResult[];
  timing_ms: SearchTiming;
  debug?: DebugInfo;
  fallback_from?: SearchMode;
  fallback_reason?: string;
}

export interface HealthResponse {
  status: string;
  retrieval?: { qdrant_available?: boolean; dense_search?: string };
}

export interface DocumentInfo {
  id: string;
  report_code: string;
  title: string;
  domain: string;
  status: string;
  completed_at: string | null;
  source_path: string;
  file_name: string;
  indexed_at: string | null;
}

export interface DocumentDetail extends DocumentInfo {
  chunk_count: number;
  section_count: number;
}

export interface DocumentsResponse {
  documents: DocumentInfo[];
  total: number;
}

export interface Section {
  id: string;
  parent_section_id: string | null;
  level: number;
  heading: string;
  heading_path: string;
  section_type: string;
  ordinal: number;
  start_line: number;
  end_line: number;
}

export interface SectionsResponse {
  document_id: string;
  sections: Section[];
}

export interface ChunkDetail {
  id: string;
  document_id: string;
  section_id: string;
  ordinal: number;
  heading_path: string;
  content_type: string;
  raw_markdown: string;
  plain_text: string;
  evidence_level: number | null;
  start_line: number;
  end_line: number;
  title: string | null;
}

export interface IndexCounts {
  documents: number;
  sections: number;
  chunks: number;
  fts_terms: number;
  fts_trigram: number;
  qdrant_points: number;
}

export interface InferenceWorker {
  alive: boolean;
  device: string;
  device_kind: string;
  fallback_to_cpu: boolean;
  total_restarts: number;
}

export interface IndexStatus {
  counts: IndexCounts;
  consistent: boolean;
  last_full_scan: string | null;
  inference_worker: InferenceWorker;
}

export interface EvalSummaryMetrics {
  hit1: number;
  hit3: number;
  hit5: number;
  recall5: number;
  recall10: number;
  mrr: number;
  ndcg: number;
  p50: number;
  p95: number;
}

export interface EvaluationResults {
  n_queries: number;
  corpus: Record<string, unknown>;
  summary: Record<string, EvalSummaryMetrics>;
  per_type: Record<string, Record<string, unknown>>;
  gate: Record<string, boolean>;
  best_arm: string;
  index_seconds: number;
}

export interface EvaluationLatest {
  results: EvaluationResults;
  report_markdown: string | null;
}

export type SettingsPayload = Record<string, unknown>;

export type TaskStatus =
  | 'READY'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'FAILED'
  | 'INVALID_RESULT'
  | 'IMPORTED'
  | 'ARCHIVED';

export type TaskType = 'summary' | 'comparison' | 'causal_synthesis' | 'tension_extraction';
export type EvidenceContextMode = 'none' | 'neighbor_1' | 'section';

export interface TaskInfo {
  task_id: string;
  task_path: string;
  status: TaskStatus;
  task_type: TaskType | null;
  query: string | null;
  created_at: string | null;
  evidence_count: number | null;
  worker: string | null;
  model: string | null;
  completed_at: string | null;
  stale: boolean;
  error: string | null;
}

export interface TaskListResponse {
  tasks: TaskInfo[];
  count: number;
}

export interface ExternalRunSummary {
  run_id: string;
  task_count: number;
  path: string;
}

export interface ExternalRunTask {
  task_id: string;
  status: string;
  task_type: TaskType | null;
  query: string | null;
  worker: string | null;
  model: string | null;
  completed_at: string | null;
  claims_count: number;
  tensions_count: number;
}

export interface ExternalRunsResponse {
  runs: ExternalRunSummary[];
  count: number;
}

export interface ExternalRunDetail {
  run_id: string;
  path: string;
  task_count: number;
  tasks: ExternalRunTask[];
}

export interface EvidenceRefInput {
  source_type: 'report' | 'cognition';
  document_id: string;
  section_id?: string | null;
  chunk_id: string;
  content_hash?: string | null;
  title?: string | null;
  heading_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  evidence_level?: number | null;
  excerpt?: string | null;
}

export interface CognitionContextInput {
  schema_version?: '1.0';
  context_id: string;
  object_type: string;
  object_id: string;
  content_hash?: string | null;
  title?: string | null;
  excerpt?: string | null;
}

export interface CreateTaskRequest {
  task_type: TaskType;
  query: string;
  evidence_refs: EvidenceRefInput[];
  evidence_context_mode?: EvidenceContextMode;
  dossier_id?: string | null;
  cognition_object_ids?: string[];
  cognition_context?: CognitionContextInput[];
}

export interface CreateTaskResponse {
  task_id: string;
  status: TaskStatus;
  task_path: string;
  dossier_id?: string | null;
  research_context_included?: boolean;
  cognition_context_count?: number;
}

export interface GateDetail {
  name: string;
  passed: boolean;
  failure: string | null;
}

export interface RescanResponse {
  task_id: string;
  passed: boolean;
  status: TaskStatus;
  gates: GateDetail[];
  stale: boolean;
  citation_coverage: number | null;
  unsupported_claim_rate: number | null;
}

export interface SynthesisClaim {
  id: string;
  text: string;
  epistemic_state: string;
  evidence_refs: string[];
  rationale?: string | null;
}

export interface SynthesisTension {
  id: string;
  text: string;
  epistemic_state?: string | null;
  evidence_refs: string[];
}

export interface TaskResultEnvelope {
  schema_version?: string;
  task_id?: string;
  task_type?: TaskType;
  query?: string;
  summary?: string;
  claims?: SynthesisClaim[];
  tensions?: SynthesisTension[];
  uncertainties?: string[];
  open_questions?: string[];
  additional_evidence_needed?: Array<{ question: string; reason: string }>;
  worker?: { tool?: string; model?: string | null };
  generated_at?: string;
  [key: string]: unknown;
}

export interface TaskDetail extends TaskInfo {
  result?: TaskResultEnvelope | null;
  research_context?: Record<string, unknown> | null;
  research_brief_available?: boolean;
}

export interface PromptResponse {
  task_id: string;
  file: string;
  content: string;
  sha256: string;
}

export interface CognitionProposalPayload {
  title: string;
  origin_type: 'external_llm';
  origin_ref: string;
  origin_title: string;
  generator: string;
  description: string;
  topics: string[];
  items: Array<Record<string, unknown>>;
}

export interface ProposalCandidatesResponse {
  task_id: string;
  source_status: 'COMPLETED' | 'IMPORTED';
  auto_apply: false;
  target_contract: string;
  proposal_payload: CognitionProposalPayload;
  warnings: string[];
}

export interface CognitionHealthResponse {
  reachable: boolean;
  api_url: string;
  settings?: Record<string, unknown>;
  error?: string;
}

export interface ProposalPublication {
  schema_version: string;
  task_id: string;
  proposal_id: string;
  origin_ref: string | null;
  published_at: string;
  cognition_api_url: string;
  auto_apply: false;
}

export interface ProposalPublicationResponse {
  task_id: string;
  published: boolean;
  reused?: boolean;
  publication: ProposalPublication | null;
  warnings?: string[];
  auto_apply?: false;
}

export interface JobInfo {
  job_id: string;
  kind: string;
  status: string;
  [key: string]: unknown;
}
