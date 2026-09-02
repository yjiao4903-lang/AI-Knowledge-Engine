// 类型化 API client。所有请求走 /api 前缀（Vite dev server 代理到 127.0.0.1:8765）。
import type {
  ChunkDetail,
  CognitionHealthResponse,
  CreateTaskRequest,
  CreateTaskResponse,
  DocumentDetail,
  DocumentsResponse,
  EvaluationLatest,
  ExternalRunDetail,
  ExternalRunsResponse,
  HealthResponse,
  IndexStatus,
  PromptResponse,
  ProposalCandidatesResponse,
  ProposalPublicationResponse,
  RescanResponse,
  RetrievalFeedbackBatch,
  RetrievalFeedbackResponse,
  SearchRequest,
  SearchResponse,
  SectionsResponse,
  SettingsPayload,
  TaskDetail,
  TaskListResponse,
} from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (e) {
    throw new ApiError(0, 'NETWORK', `无法连接后端 API（127.0.0.1:8765）：${String(e)}`);
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const b = (body ?? {}) as Record<string, unknown>;
    const detail = b.detail;
    const message =
      (b.message as string | undefined) ??
      (typeof detail === 'string' ? detail : undefined) ??
      (detail !== undefined ? JSON.stringify(detail) : undefined) ??
      (res.statusText || `HTTP ${res.status}`);
    throw new ApiError(res.status, (b.error as string | undefined) ?? `HTTP_${res.status}`, message, detail);
  }
  return body as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  search: (req: SearchRequest) => post<SearchResponse>('/api/search', req),
  retrievalFeedback: (batch: RetrievalFeedbackBatch) =>
    post<RetrievalFeedbackResponse>('/api/retrieval-feedback', batch),

  documents: () => request<DocumentsResponse>('/api/documents'),
  document: (id: string) => request<DocumentDetail>(`/api/documents/${encodeURIComponent(id)}`),
  sections: (id: string) => request<SectionsResponse>(`/api/documents/${encodeURIComponent(id)}/sections`),
  chunk: (chunkId: string) => request<ChunkDetail>(`/api/chunks/${encodeURIComponent(chunkId)}`),
  openOriginal: (id: string) =>
    post<{ opened: boolean; path: string }>(`/api/documents/${encodeURIComponent(id)}/open-original`),

  indexStatus: () => request<IndexStatus>('/api/index/status'),
  scan: () => post<Record<string, unknown>>('/api/index/scan'),
  reindexDocument: (id: string) =>
    post<Record<string, unknown>>(`/api/index/reindex-document/${encodeURIComponent(id)}`),

  settings: () => request<SettingsPayload>('/api/settings'),
  evaluationLatest: () => request<EvaluationLatest>('/api/evaluation/latest'),

  createTask: (req: CreateTaskRequest) => post<CreateTaskResponse>('/api/synthesis/tasks', req),
  listTasks: () => request<TaskListResponse>('/api/synthesis/tasks'),
  task: (id: string) => request<TaskDetail>(`/api/synthesis/tasks/${encodeURIComponent(id)}`),
  taskProposalCandidates: (id: string) =>
    request<ProposalCandidatesResponse>(`/api/synthesis/tasks/${encodeURIComponent(id)}/proposal-candidates`),
  rescanTask: (id: string) =>
    post<RescanResponse>(`/api/synthesis/tasks/${encodeURIComponent(id)}/rescan`),
  archiveTask: (id: string) =>
    post<{ task_id: string; status: string; task_path: string }>(
      `/api/synthesis/tasks/${encodeURIComponent(id)}/archive`,
    ),
  openTaskFolder: (id: string) =>
    post<{ opened: boolean; path: string }>(
      `/api/synthesis/tasks/${encodeURIComponent(id)}/open-folder`,
    ),
  taskPrompt: (id: string) =>
    request<PromptResponse>(`/api/synthesis/tasks/${encodeURIComponent(id)}/prompt`),

  cognitionHealth: () => request<CognitionHealthResponse>('/api/research-os/cognition/health'),
  taskProposalPublication: (id: string) =>
    request<ProposalPublicationResponse>(
      `/api/research-os/tasks/${encodeURIComponent(id)}/proposal-publication`,
    ),
  publishTaskProposal: (id: string, force = false) =>
    post<ProposalPublicationResponse>(
      `/api/research-os/tasks/${encodeURIComponent(id)}/publish-proposal`,
      { force },
    ),

  externalRuns: () => request<ExternalRunsResponse>('/api/taskpack/runs'),
  externalRun: (id: string) =>
    request<ExternalRunDetail>(`/api/taskpack/runs/${encodeURIComponent(id)}`),
};
