/**
 * The paper record's two reads (ADR 0037 / 0053 amendment 2026-10-09): `Query.edgeDesk`, the
 * Ideas signals of the edges the user follows (what to buy, what to sell next session, each
 * followed edge's live record), and `Query.edgePaper`, one edge's live record against the
 * backtest's usual range, its paper trades and a trial's forward test. Every figure, sentence
 * and bar is the server's; the cache holds the responses.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, queryKeys, TypedDocumentString } from '@/shared/api';

import type { Desk, EdgePaper, LiveState } from '../model/paper';

// Compact documents as TypedDocumentString (not `graphql()`): the generated operation map is in
// the entry chunk, and these two reads load with their pages.
const DESK_TRADE = 'edgeId edgeName instrumentId instrument { symbol } rank buySession sellSession';
const EdgeDesk = new TypedDocumentString<{ edgeDesk: Desk | null }, Record<string, never>>(
  `query EdgeDesk { edgeDesk { session sellSession buys { ${DESK_TRADE} } sells { ${DESK_TRADE} }
    followed { edgeId name state tonight tonightReason missed
      record { state closed open winRate } }
    liveStates { edgeId name state closed winRate headline followed } } }`,
);

const SIDE = 'closed wins winRate';
const EdgePaper = new TypedDocumentString<{ edgePaper: EdgePaper | null }, { id: string }>(
  `query EdgePaper($id: String!) { edgePaper(id: $id) {
    record { state closed wins open skipped winRate backtestRate basis low high headline
      bins { start end chance } }
    trades { instrumentId instrument { symbol } rank signalSession buySession sellSession status
      reason excessReturn }
    forward { replaces replacesName since sessions needed headline this { ${SIDE} }
      replaced { ${SIDE} } } } }`,
);

/** The signals of the edges the user follows (null: nothing stored for the session). */
export function useEdgeDesk() {
  return useQuery({ ...edgeDeskQuery(), select: (data) => data.edgeDesk });
}

function edgeDeskQuery() {
  return queryOptions({
    queryKey: queryKeys.gql('EdgeDesk', {}),
    queryFn: ({ queryKey }) => gql(EdgeDesk, {}, queryKey),
  });
}

/** Start the desk's read before the page mounts (a route loader); the hooks then join it. */
export function prefetchEdgeDesk(client: QueryClient): void {
  void client.query(edgeDeskQuery()).catch(() => undefined);
}

/** One edge's paper record (null: no such edge, or nothing stored). */
export function useEdgePaper(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgePaper', { id }),
    queryFn: ({ queryKey }) => gql(EdgePaper, { id }, queryKey),
    select: (data) => data.edgePaper,
  });
}

/** The live state of every edge with a record, the followed ones and the site's (the desk's own read: one load per page; empty when nothing is stored). */
export function useEdgeLiveStates() {
  return useQuery({
    ...edgeDeskQuery(),
    select: (data): LiveState[] => data.edgeDesk?.liveStates ?? [],
  });
}
