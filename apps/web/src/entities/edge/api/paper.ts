/**
 * The paper record's two reads (ADR 0037 / 0053 amendment 2026-10-09): `Query.edgeDesk`, the
 * Ideas signals of the edges the user follows (what to buy, what to sell next session, each
 * followed edge's live record), and `Query.edgePaper`, one edge's live record against the
 * backtest's usual range, its paper trades and a trial's forward test. Every figure, sentence
 * and bar is the server's; the cache holds the responses.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const EdgeDesk = graphql(`
  query EdgeDesk {
    edgeDesk {
      session
      sellSession
      buys {
        edgeId
        edgeName
        instrumentId
        instrument {
          symbol
        }
        rank
        buySession
        sellSession
      }
      sells {
        edgeId
        edgeName
        instrumentId
        instrument {
          symbol
        }
        rank
        buySession
        sellSession
      }
      followed {
        edgeId
        name
        state
        tonight
        tonightReason
        missed
        record {
          state
          closed
          open
          winRate
        }
      }
    }
  }
`);

const EdgePaper = graphql(`
  query EdgePaper($id: String!) {
    edgePaper(id: $id) {
      edgeId
      record {
        state
        closed
        wins
        open
        skipped
        winRate
        backtestRate
        basis
        low
        high
        headline
        bins {
          start
          end
          chance
        }
      }
      trades {
        instrumentId
        instrument {
          symbol
        }
        rank
        signalSession
        buySession
        sellSession
        status
        reason
        excessReturn
      }
      forward {
        replaces
        replacesName
        since
        sessions
        needed
        canReplace
        headline
        this {
          closed
          wins
          winRate
        }
        replaced {
          closed
          wins
          winRate
        }
      }
    }
  }
`);

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
