/**
 * Run an edge evaluation on request (POST /edges/{id}/evaluate) and follow it: the API starts the
 * CLI's `edge-eval` job (202, or 409 while another of the user's evaluations runs) and the job is
 * polled until it finishes, then the edges are read again. `asSite`: an admin's site run.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { refreshEdges } from '@/entities/edge';
import { api, queryKeys, unwrap } from '@/shared/api';

import { isActive } from '../model/evaluation';

/** How often a requested evaluation is polled while it is queued or running. */
export const EVALUATION_POLL_MS = 3000;

export function useRunEvaluation(id: string) {
  const client = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: (asSite: boolean) =>
      unwrap(
        api.POST('/edges/{edge_id}/evaluate', {
          params: { path: { edge_id: id }, query: { as_site: asSite } },
        }),
      ),
    onSuccess: (run) => {
      setJobId(run.job_id);
    },
  });
  const status = useQuery({
    queryKey: queryKeys.edges.evaluation(id, jobId ?? ''),
    queryFn: () => unwrap(api.GET('/jobs/{job_id}', { params: { path: { job_id: jobId ?? '' } } })),
    enabled: jobId !== null,
    refetchInterval: (query) => (isActive(query.state.data) ? EVALUATION_POLL_MS : false),
    retry: false,
  });
  const run = status.data ?? start.data;
  const finished = status.data !== undefined && !isActive(status.data);
  useEffect(() => {
    if (finished) void refreshEdges(client);
  }, [finished, client]);
  return {
    start: (asSite = false) => {
      start.mutate(asSite);
    },
    run,
    running: start.isPending || isActive(run),
    error: start.error ?? status.error,
  };
}
