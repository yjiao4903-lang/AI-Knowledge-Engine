// API 响应类型（依据 docs/HANDOFF_M11.md §2 真实契约建模）
// 注意：scores.reranker / pre_rerank_rank 在 rerank=false 时为 null；
// evidence_level 可能为 null（unmarked）；debug 仅在 options.debug=true 时存在。

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
  sources: {
    dense: unknown[];
    terms: unknown[];
    trigram: unknown[];
  };
  boosted_sections: unknown[];
  candidates_before_filter: number;
  fused_top: unknown[];
  rerank: unknown[];
}

export interface SearchResponse {
  query: string;
  mode: string;
  results: SearchResult[];
  timing_ms: SearchTiming;
  debug?: DebugInfo;
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

export interface JobInfo {
  job_id: string;
  kind: string;
  status: string;
  [key: string]: unknown;
}
