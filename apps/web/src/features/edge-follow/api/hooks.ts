/**
 * The writes of a user's edges (ADR 0053 amendment, `/edges/{id}`): copy an edge, or make a new
 * version of it (a new edge of theirs that extends it), move their status about one (follow a site edge; reject, retire, reopen their own) and show a
 * copy's out-of-sample result, and the admin's read of one edge as the TOML to land in the site's
 * config. Each write reads the edges again.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { refreshEdges } from '@/entities/edge';
import { api, gql, TypedDocumentString, unwrap } from '@/shared/api';

/** Written by hand, not through `graphql()`: the admin's one-off download stays out of the
 * generated document map the entry chunk carries. */
const PublishedEdge = new TypedDocumentString<
  { publishedEdgeDocument?: string | null },
  { id: string }
>('query PublishedEdge($id: String!) { publishedEdgeDocument(id: $id) }');

/** Copy `id` under a new name; `asVersion`: the copy is a trial that would replace it. */
export function useCopyEdge(id: string, asVersion = false) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (newId: string) =>
      unwrap(
        api.POST('/edges/{edge_id}/copy', {
          params: { path: { edge_id: id } },
          body: { new_id: newId, as_version: asVersion },
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

// Until the controls speak status (PR 4): the move's state word as the API takes it, a bookmark
// for a site edge, the status for the user's own.
const OWN_STATUS: Record<string, string> = {
  researching: 'researching',
  trial: 'candidate',
  following: 'live',
  rejected: 'rejected',
  retired: 'retired',
};

export const moveBody = (state: string | undefined, mine: boolean) => {
  if (state === undefined) return { follow: null, status: null };
  return mine
    ? { follow: null, status: OWN_STATUS[state] ?? state }
    : { follow: state === 'following' || state === 'trial', status: null };
};

export function useMoveEdge(id: string, mine = false) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ state, reason = '', revealOos = false }: StateMove) =>
      unwrap(
        api.PUT('/edges/{edge_id}/state', {
          params: { path: { edge_id: id } },
          body: { ...moveBody(state, mine), reason, reveal_oos: revealOos },
        }),
      ),
    onSuccess: () => refreshEdges(client),
  });
}

/** The edge as one TOML document (admin only: the API refuses anyone else); null: none. */
export const publishedDocument = async (id: string): Promise<string | null> =>
  (await gql(PublishedEdge, { id })).publishedEdgeDocument ?? null;
