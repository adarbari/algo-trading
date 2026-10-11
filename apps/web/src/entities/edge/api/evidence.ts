/**
 * The evidence reads of an edge's verdict basis (ADR 0064 / 0065): `Query.edgeTrades` (one page of
 * the trade ledger for a period, sorted by the server; the CSV file is the same rows at
 * `/files/edges/{id}/trades.csv`) and `Query.edgeVariants` (the grid of every screen and holding
 * period tried, the basis marked official). The basis is the verdict's, resolved by the server:
 * the web passes no run, screen or horizon.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { EdgeTradePage, EdgeVariants, TradePeriod, TradeSort } from '../model/evidence';

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

const EdgeVariantGrid = graphql(`
  query EdgeVariantGrid($edgeId: String!) {
    edgeVariants(edgeId: $edgeId) {
      basis
      trials
      oosHidden
      unknown {
        code
        kind
        guideTerm
        kindText
      }
      rows {
        edgeVariant
        variant
        horizonSessions
        inSample {
          winRate
          baseRate
          liftPts
          decileSpread
          trades
        }
        outOfSample {
          winRate
          baseRate
          liftPts
          decileSpread
          trades
        }
        all {
          winRate
          baseRate
          liftPts
          decileSpread
          trades
        }
        official
        notPreChosen
        modelFit
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
    select: (data) => data.edgeTrades as EdgeTradePage | null,
    placeholderData: keepPreviousData,
  });
}

/** The variant grid of the edge's official run (null: no such edge). */
export function useEdgeVariants(edgeId: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeVariantGrid', { edgeId }),
    queryFn: () => gql(EdgeVariantGrid, { edgeId }),
    select: (data) => data.edgeVariants as EdgeVariants | null,
  });
}
