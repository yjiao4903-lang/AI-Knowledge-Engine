import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { CandidateTaskRequest, TopicCandidateStatus } from './topicCandidateTypes';

export function useTopicCandidates(dossierId: string | undefined) {
  return useQuery({
    queryKey: ['topicCandidates', dossierId],
    queryFn: () => api.topicCandidates(dossierId!),
    enabled: Boolean(dossierId),
    staleTime: 10_000,
  });
}

export function useRefreshTopicCandidates(dossierId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.refreshTopicCandidates(dossierId!),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['topicCandidates', dossierId] });
      void qc.invalidateQueries({ queryKey: ['researchDossier', dossierId] });
    },
  });
}

export function useReviewTopicCandidate(dossierId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      candidateId,
      status,
      reason,
    }: {
      candidateId: string;
      status: TopicCandidateStatus;
      reason?: string;
    }) => api.reviewTopicCandidate(dossierId!, candidateId, { status, reason, reviewer: 'user' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['topicCandidates', dossierId] });
    },
  });
}

export function useCreateTopicCandidateTask(
  dossierId: string | undefined,
  candidateId: string | undefined,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CandidateTaskRequest) =>
      api.createTopicCandidateTask(dossierId!, candidateId!, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['topicCandidates', dossierId] });
      void qc.invalidateQueries({ queryKey: ['tasks'] });
    },
  });
}
