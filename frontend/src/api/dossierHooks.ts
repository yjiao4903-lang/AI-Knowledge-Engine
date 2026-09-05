import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { DossierUpsertRequest } from './dossierTypes';

export function useDossiers() {
  return useQuery({
    queryKey: ['researchDossiers'],
    queryFn: () => api.dossiers(),
    staleTime: 15_000,
  });
}

export function useDossier(id: string | undefined) {
  return useQuery({
    queryKey: ['researchDossier', id],
    queryFn: () => api.dossier(id!),
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useUpsertDossier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DossierUpsertRequest }) =>
      api.upsertDossier(id, body),
    onSuccess: (detail) => {
      qc.setQueryData(['researchDossier', detail.dossier.dossier_id], detail);
      void qc.invalidateQueries({ queryKey: ['researchDossiers'] });
    },
  });
}
