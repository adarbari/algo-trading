/**
 * The writes of a user's edges (ADR 0053 amendment, `/edges/{id}`): copy an edge (a new edge of
 * theirs that extends it), move their state about one (follow, reject, retire, reopen) and show a
 * copy's out-of-sample result, and the admin's read of one edge as the TOML to land in the site's
 * config. Each write reads the edges again.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { refreshEdges } from '@/entities/edge';
import { api, gql, graphql, unwrap } from '@/shared/api';

const PublishedEdge = graphql(`
  query PublishedEdge($id: String!) {
    publishedEdgeDocument(id: $id)
  }
`);

export function useCopyEdge(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (newId: string) =>
      unwrap(
        api.POST('/edges/{edge_id}/copy', {
          params: { path: { edge_id: id } },
          body: { new_id: newId, as_version: false },
        }),
      ),
    onSuccess: () => refreshEdges(client),
  });
}

export interface StateMove {
  /** The new state; none keeps it (only a reveal). */
  state?: string;
  reason?: string;
  revealOos?: boolean;
}

export function useMoveEdge(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ state, reason = '', revealOos = false }: StateMove) =>
      unwrap(
        api.PUT('/edges/{edge_id}/state', {
          params: { path: { edge_id: id } },
          body: { state: state ?? null, reason, reveal_oos: revealOos },
        }),
      ),
    onSuccess: () => refreshEdges(client),
  });
}

/** The edge as one TOML document (admin only: the API refuses anyone else); null: none. */
export const publishedDocument = async (id: string): Promise<string | null> =>
  (await gql(PublishedEdge, { id })).publishedEdgeDocument ?? null;
