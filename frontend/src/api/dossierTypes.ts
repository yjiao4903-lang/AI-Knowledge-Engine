export interface DossierEvidenceRef {
  schema_version?: string;
  source_type: string;
  document_id: string;
  section_id?: string | null;
  chunk_id: string;
  content_hash?: string | null;
  title?: string | null;
  heading_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
}

export interface DossierDefinition {
  schema_version: string;
  dossier_id: string;
  title: string;
  direction: string;
  scope_include: string[];
  scope_exclude: string[];
  topic_object_id: string | null;
  question_ids: string[];
  judgment_ids: string[];
  other_cognition_ids: string[];
  evidence_refs: DossierEvidenceRef[];
  updated_at: string;
}

export interface DossierUpsertRequest {
  title: string;
  direction?: string;
  scope_include?: string[];
  scope_exclude?: string[];
  topic_object_id?: string | null;
  question_ids?: string[];
  judgment_ids?: string[];
  other_cognition_ids?: string[];
  evidence_refs?: DossierEvidenceRef[];
}

export interface DossierListItem {
  dossier_id: string;
  title: string;
  direction: string;
  formal_topic_bound: boolean;
  updated_at: string;
}

export interface DossierListResponse {
  dossiers: DossierListItem[];
}

export interface DossierCognitionSource {
  object_id: string;
  role: string;
  title?: string | null;
  content_hash?: string | null;
  indexed_at?: string | null;
  source_bucket?: string | null;
  excerpt?: string;
  missing: boolean;
}

export interface DossierEvidenceSource {
  source_type?: string;
  document_id?: string;
  section_id?: string | null;
  chunk_id: string;
  content_hash?: string | null;
  title?: string | null;
  heading_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  excerpt?: string;
  missing: boolean;
}

export interface DossierSources {
  topic: DossierCognitionSource[];
  questions: DossierCognitionSource[];
  judgments: DossierCognitionSource[];
  other_cognition: DossierCognitionSource[];
  evidence: DossierEvidenceSource[];
}

export interface DossierSourceChange {
  source: string;
  change: 'changed' | 'missing' | 'new';
  saved: string | null;
  current: string | null;
}

export interface DossierDetail {
  schema_version: string;
  dossier: DossierDefinition;
  formal_topic_bound: boolean;
  planning_only: boolean;
  generated_at: string;
  semantic_required: boolean;
  needs_refresh: boolean;
  source_changes: DossierSourceChange[];
  sources: DossierSources;
  source_versions: Record<string, string | null>;
  last_saved_snapshot: Record<string, unknown> | null;
}
