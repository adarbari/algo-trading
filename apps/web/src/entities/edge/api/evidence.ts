/**
 * The trade ledger of an edge's verdict basis (ADR 0064 / 0065): `Query.edgeTrades`, one page of
 * the trades for a period, sorted by the server (the CSV file is the same rows at
 * `/files/edges/{id}/trades.csv`). The basis is the verdict's, resolved by the server: the web
 * passes no run, screen or horizon.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { TradePeriod, TradeSort } from '../model/evidence';

const EdgeTrades = graphql(`
  query EdgeTrades(
    $edgeId: String!
    $period: TradePeriod!
    $page: Int!
    $sort: TradeSort!
    $descending: Boolean!
  ) {
    edgeTrades(
      edgeId: $edgeId
      period: $period
      page: $page
      sort: $sort
      descending: $descending
    ) {
      period
      page
      pageSize
      total
      basis
      licence
      oosHidden
      symbolsSnapshot
      unknown {
        code
        kind
        guideTerm
        kindText
      }
      rows {
        variant
        horizonSessions
        decisionSession
        entrySession
        exitSession
        instrumentId
        symbol {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
        company {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
        symbolAsOf
        rank
        status
        excludedReason
        hit
        delisted
        beforeSplit
        source
        score {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
        value {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
        grossValue {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
        maxDrawdown
        advUsd {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
        reference {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
        touch {
          value
          unknown {
            code
            kind
            guideTerm
            kindText
          }
        }
      }
    }
  }
`);

export type TradesRequest = {
  edgeId: string;
  period: TradePeriod;
  page: number;
  sort: TradeSort;
  descending: boolean;
};

/** One page of the verdict basis's trades (null: no such edge). Keeps the previous page while the next loads. */
export function useEdgeTrades(request: TradesRequest) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeTrades', request),
    queryFn: () => gql(EdgeTrades, request),
    select: (data) => data.edgeTrades,
    placeholderData: keepPreviousData,
  });
}
