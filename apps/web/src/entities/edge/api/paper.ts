/**
 * The paper record's two reads (ADR 0037 / 0053 amendment 2026-10-09): `Query.edgeDesk`, the
 * Ideas signals of the edges the user follows (what to buy, what to sell next session, each
 * followed edge's live record), and `Query.edgePaper`, one edge's live record against the
 * backtest's usual range, its paper trades and a trial's forward test. Every figure, sentence
 * and bar is the server's; the cache holds the responses.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, queryKeys, TypedDocumentString } from '@/shared/api';

import type { Desk, EdgePaper } from '../model/paper';

// Compact documents as TypedDocumentString (not `graphql()`): the generated operation map is in
// the entry chunk, and these two reads load with their pages.
const DESK_TRADE = 'edgeId edgeName instrumentId instrument { symbol } rank buySession sellSession';
const EdgeDesk = new TypedDocumentString<{ edgeDesk: Desk | null }, Record<string, never>>(
  `query EdgeDesk { edgeDesk { session sellSession buys { ${DESK_TRADE} } sells { ${DESK_TRADE} }
    followed { edgeId name state tonight tonightReason missed
      record { state closed open winRate } } } }`,
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
  return useQuery({
    queryKey: queryKeys.gql('EdgeDesk', {}),
    queryFn: () => gql(EdgeDesk, {}),
    select: (data) => data.edgeDesk,
  });
}

/** One edge's paper record (null: no such edge, or nothing stored). */
export function useEdgePaper(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgePaper', { id }),
    queryFn: () => gql(EdgePaper, { id }),
    select: (data) => data.edgePaper,
  });
}
