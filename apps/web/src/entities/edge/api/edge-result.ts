/**
 * The sections of an edge's result (ADR 0037 / 0064 / 0065): `Query.edgeResult`, one document per
 * section so a page reads only the sections it shows (each resolves lazily on the server, about the
 * verdict's own run and basis, which the page never passes): the basis, the evidence curve with its
 * live stroke, the drawdown, the rolling starts, the monthly map and the decay with its live bar.
 * `date` resolves the session of the live stroke and bar only. Every number, date and state is the
 * server's; the browser derives nothing from them. The cache holds each response.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const ResultBasis = graphql(`
  query EdgeResultBasis($id: String!, $date: Date) {
    edgeResult(id: $id, date: $date) {
      basis {
        runId
        variant
        horizonSessions
        splitFrom
        oosHidden
        unknown {
          kind
          guideTerm
          kindText
        }
      }
    }
  }
`);

const ResultCurve = graphql(`
  query EdgeResultCurve($id: String!, $date: Date) {
    edgeResult(id: $id, date: $date) {
      curve {
        kind
        unit
        splitFrom
        hidden
        points {
          decision
          exit
          period
          value
          cumulative
          baseValue
          baseCumulative
          trades
          weight
        }
        gaps {
          from
          to
          kind
          unknown {
            kind
            guideTerm
            kindText
          }
        }
        live {
          state
          since
          anchor
          closed
          sessions
          points {
            sell
            value
            cumulative
            trades
          }
        }
        unknown {
          kind
          guideTerm
          kindText
        }
      }
    }
  }
`);

const ResultDrawdown = graphql(`
  query EdgeResultDrawdown($id: String!) {
    edgeResult(id: $id) {
      drawdown {
        unit
        points {
          exit
          depth
        }
        episodes {
          peak
          trough
          recovered
          depth
        }
        maxInSample
        maxOutOfSample
        volInSample
        volOutOfSample
        unknown {
          kind
          guideTerm
          kindText
        }
      }
    }
  }
`);

const ResultRollingStarts = graphql(`
  query EdgeResultRollingStarts($id: String!) {
    edgeResult(id: $id) {
      rollingStarts {
        unit
        starts {
          start
          trades
          liftPts
          meanExcess
        }
        unknown {
          kind
          guideTerm
          kindText
        }
      }
    }
  }
`);

const ResultMonthly = graphql(`
  query EdgeResultMonthly($id: String!) {
    edgeResult(id: $id) {
      monthly {
        unit
        months {
          month
          value
          trades
          period
        }
        unknown {
          kind
          guideTerm
          kindText
        }
      }
    }
  }
`);

const ResultDecay = graphql(`
  query EdgeResultDecay($id: String!, $date: Date) {
    edgeResult(id: $id, date: $date) {
      decay {
        measure
        unit
        basisHorizon
        published {
          measure
          value
          horizonSessions
          sample
          source {
            title
            url
          }
        }
        bars {
          period
          value
          n
          state
        }
      }
    }
  }
`);

/** The run and basis every section reads (null: no such edge). */
export function useEdgeResultBasis(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultBasis', { id }),
    queryFn: () => gql(ResultBasis, { id }),
    select: (data) => data.edgeResult?.basis ?? null,
  });
}

/** The evidence curve and its live stroke (null: no such edge). */
export function useEdgeCurve(id: string, date?: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultCurve', { id, date }),
    queryFn: () => gql(ResultCurve, { id, date }),
    select: (data) => data.edgeResult?.curve ?? null,
  });
}

/** The drawdown and the volatility of the windows (null: no such edge). */
export function useEdgeDrawdown(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultDrawdown', { id }),
    queryFn: () => gql(ResultDrawdown, { id }),
    select: (data) => data.edgeResult?.drawdown ?? null,
  });
}

/** The lift from each year's start forward (null: no such edge). */
export function useEdgeRollingStarts(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultRollingStarts', { id }),
    queryFn: () => gql(ResultRollingStarts, { id }),
    select: (data) => data.edgeResult?.rollingStarts ?? null,
  });
}

/** The calendar months of the curve (null: no such edge). */
export function useEdgeMonthly(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultMonthly', { id }),
    queryFn: () => gql(ResultMonthly, { id }),
    select: (data) => data.edgeResult?.monthly ?? null,
  });
}

/** The decay with its live bar (null: no such edge, or the verdict has no basis). */
export function useEdgeDecay(id: string, date?: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultDecay', { id, date }),
    queryFn: () => gql(ResultDecay, { id, date }),
    select: (data) => data.edgeResult?.decay ?? null,
  });
}
