// TanStack Query hooks：数据获取与缓存。
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { ChunkDetail, CreateTaskRequest, Section, SearchRequest } from './types';

export function useDocuments() {
  return useQuery({ queryKey: ['documents'], queryFn: () => api.documents(), staleTime: 60_000 });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: ['document', id],
    queryFn: () => api.document(id!),
    enabled: !!id,
    retry: (count, error) =>
      !(error instanceof Error && 'status' in error && (error as { status: number }).status === 404) && count < 2,
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
  return useQuery({ queryKey: ['indexStatus'], queryFn: () => api.indexStatus(), refetchInterval: 15_000 });
}

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => api.settings(), staleTime: 5 * 60_000 });
}

export function useEvaluationLatest() {
  return useQuery({ queryKey: ['evaluationLatest'], queryFn: () => api.evaluationLatest(), staleTime: 60_000 });
}

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => api.health(), refetchInterval: 15_000 });
}

export function useSearch(qdrantAvailable?: boolean) {
  return useMutation({
    mutationFn: async (req: SearchRequest) => {
      const requested = req.options?.mode ?? 'lexical';
      const fallback = async (reason: string) => {
        const response = await api.search({ ...req, options: { ...req.options, mode: 'lexical', rerank: false } });
        return { ...response, fallback_from: requested, fallback_reason: reason };
      };
      if (requested !== 'lexical' && qdrantAvailable === false) {
        return fallback('Qdrant 不可用（health 状态）');
      }
      try {
        return await api.search(req);
      } catch (error) {
        if (requested !== 'lexical' && (error as { status?: number }).status === 503) {
          return fallback((error as Error).message);
        }
        throw error;
      }
    },
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
  return useMutation({ mutationFn: (id: string) => api.openOriginal(id) });
}

// ---------------- TaskPack / Research OS Integration ----------------

export function useTasks() {
  return useQuery({
    queryKey: ['synthesisTasks'],
    queryFn: () => api.listTasks(),
    refetchInterval: 15_000,
  });
}

export function useTaskDetail() {
  return useMutation({ mutationFn: (id: string) => api.task(id) });
}

export function useExternalRuns() {
  return useQuery({ queryKey: ['externalTaskpackRuns'], queryFn: () => api.externalRuns() });
}

export function useExternalRun(id: string) {
  return useQuery({
    queryKey: ['externalTaskpackRun', id],
    queryFn: () => api.externalRun(id),
    enabled: Boolean(id),
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateTaskRequest) => api.createTask(req),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['synthesisTasks'] }),
  });
}

export function useTaskProposalCandidates() {
  return useMutation({ mutationFn: (id: string) => api.taskProposalCandidates(id) });
}

export function useCognitionHealth() {
  return useQuery({
    queryKey: ['cognitionHealth'],
    queryFn: () => api.cognitionHealth(),
    refetchInterval: 15_000,
  });
}

export function usePublishTaskProposal() {
  return useMutation({ mutationFn: (id: string) => api.publishTaskProposal(id) });
}

export function useTaskProposalPublication() {
  return useMutation({ mutationFn: (id: string) => api.taskProposalPublication(id) });
}

export function useRescanTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.rescanTask(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['synthesisTasks'] }),
  });
}

export function useArchiveTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.archiveTask(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['synthesisTasks'] }),
  });
}

export function useOpenTaskFolder() {
  return useMutation({ mutationFn: (id: string) => api.openTaskFolder(id) });
}

export function useTaskPrompt() {
  return useMutation({ mutationFn: (id: string) => api.taskPrompt(id) });
}

/** 枚举一个文档的全部 chunk（兼容历史后端）。 */
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
        if (status === 404) break;
        throw e;
      }
      if (chunk.section_id !== sec.id) break;
      chunks.push(chunk);
      pointer = chunk.ordinal + 1;
      onProgress?.(chunks.length, 0);
    }
  }
  chunks.sort((a, b) => a.ordinal - b.ordinal);
  return chunks;
}
