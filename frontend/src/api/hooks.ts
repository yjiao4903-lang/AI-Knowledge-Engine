// TanStack Query hooks：数据获取与缓存。
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { ChunkDetail, CreateTaskRequest, Section, SearchRequest } from './types';

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: () => api.documents(),
    staleTime: 60_000,
  });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: ['document', id],
    queryFn: () => api.document(id!),
    enabled: !!id,
    retry: (count, error) => !(error instanceof Error && 'status' in error && (error as { status: number }).status === 404) && count < 2,
  });
}

export function useSections(id: string | undefined) {
  return useQuery({
    queryKey: ['sections', id],
    queryFn: () => api.sections(id!),
    enabled: !!id,
    staleTime: 5 * 60_000,
  });
}

export function useIndexStatus() {
  return useQuery({
    queryKey: ['indexStatus'],
    queryFn: () => api.indexStatus(),
    refetchInterval: 15_000,
  });
}

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => api.settings(),
    staleTime: 5 * 60_000,
  });
}

export function useEvaluationLatest() {
  return useQuery({
    queryKey: ['evaluationLatest'],
    queryFn: () => api.evaluationLatest(),
    staleTime: 60_000,
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: (req: SearchRequest) => api.search(req),
  });
}

export function useScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.scan(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['indexStatus'] });
      void qc.invalidateQueries({ queryKey: ['documents'] });
    },
  });
}

export function useReindexDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.reindexDocument(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['indexStatus'] });
      void qc.invalidateQueries({ queryKey: ['documents'] });
    },
  });
}

export function useOpenOriginal() {
  return useMutation({
    mutationFn: (id: string) => api.openOriginal(id),
  });
}

// ---------------- TaskPack Synthesis（V3.0 外部 Worker 工作流） ----------------

export function useTasks() {
  return useQuery({
    queryKey: ['synthesisTasks'],
    queryFn: () => api.listTasks(),
    refetchInterval: 15_000, // Task Center 轮询（§43：前端轮询触发 scan）
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateTaskRequest) => api.createTask(req),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['synthesisTasks'] });
    },
  });
}

export function useRescanTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.rescanTask(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['synthesisTasks'] });
    },
  });
}

export function useArchiveTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.archiveTask(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['synthesisTasks'] });
    },
  });
}

export function useOpenTaskFolder() {
  return useMutation({
    mutationFn: (id: string) => api.openTaskFolder(id),
  });
}

export function useTaskPrompt() {
  return useMutation({
    mutationFn: (id: string) => api.taskPrompt(id),
  });
}

/**
 * 枚举一个文档的全部 chunk。
 *
 * 后端只有 GET /api/chunks/{chunk_id} 单查端点，没有按文档列 chunks 的端点。
 * chunk_id 为确定性格式 {document_id}:{section_path}:{ordinal:04d}，其中 ordinal
 * 为文档级连续编号（1..chunk_count，无空洞；chunker 按 section 顺序递增，见
 * ADR-006），因此按 section 顺序、以递增指针探针即可完整枚举：
 * 每 section 从当前指针 ordinal 开始取，404 即该 section 无更多 chunk。
 * 请求量 ≈ chunk_count + section_count（全部为本地请求，代价可忽略）。
 */
export async function loadDocumentChunks(
  docId: string,
  sections: Section[],
  onProgress?: (loaded: number, totalEstimate: number) => void,
): Promise<ChunkDetail[]> {
  const chunks: ChunkDetail[] = [];
  let pointer = 1;
  for (const sec of sections) {
    const sectionPath = sec.id.startsWith(docId + ':') ? sec.id.slice(docId.length + 1) : sec.id;
    for (;;) {
      const chunkId = `${docId}:${sectionPath}:${String(pointer).padStart(4, '0')}`;
      let chunk: ChunkDetail;
      try {
        chunk = await api.chunk(chunkId);
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (status === 404) break; // 该 section 的 chunk 取完（或此 section 无 chunk）
        throw e;
      }
      if (chunk.section_id !== sec.id) break; // 归属校验：属于后续 section，指针不动
      chunks.push(chunk);
      pointer = chunk.ordinal + 1;
      onProgress?.(chunks.length, 0);
    }
  }
  chunks.sort((a, b) => a.ordinal - b.ordinal);
  return chunks;
}
