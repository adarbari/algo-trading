/**
 * The Screen Builder opened from an edge's builder (ADR 0053 amendment, ED8): the route search
 * `returnTo=<edge id>` (`NEW_EDGE` for an edge not saved yet) says where "Save and return to
 * edge" goes; the edge's draft is kept meanwhile, and the screen just made is added to it.
 */
import type { useNavigate } from '@tanstack/react-router';

/** `returnTo` of an edge that has no id yet (it cannot be an edge id: `~` is not allowed in one). */
export const NEW_EDGE = '~new';

export interface ReturnSearch {
  returnTo?: string;
}

export function validateReturnSearch(search: Record<string, unknown>): ReturnSearch {
  const { returnTo } = search;
  return typeof returnTo === 'string' && returnTo ? { returnTo } : {};
}

/** Go back to the edge's builder (adding `screen` to its screens when one was edited or made). */
export function backToEdge(
  navigate: ReturnType<typeof useNavigate>,
  returnTo: string,
  screen?: string,
): void {
  const search = screen ? { screen } : {};
  if (returnTo === NEW_EDGE) void navigate({ to: '/edges/new', search });
  else void navigate({ to: '/edges/$id/edit', params: { id: returnTo }, search });
}
