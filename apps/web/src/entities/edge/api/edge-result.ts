/**
 * The sections of an edge's result (ADR 0037 / 0064 / 0065): `Query.edgeResult`, one document per
 * section so a page reads only the sections it shows (each resolves lazily on the server, about the
 * verdict's own run and basis, which the page never passes): the basis, the evidence curve with its
 * live stroke, the drawdown, the rolling starts, the monthly map, the decay with its live bar, the
 * cost sensitivity, the capacity and where it worked (by regime, by holding period), and
 * the variant grid (`Query.edgeVariants`: every screen and holding period the run tried, the basis
 * marked official).
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
          code
          reason
          kind
          guideTerm
          kindText
          cause {
            links {
              level
              subject
              status
              message
              runId
            }
          }
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
            code
            reason
            kind
            guideTerm
            kindText
            cause {
              links {
                level
                subject
                status
                message
                runId
              }
            }
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
          code
          reason
          kind
          guideTerm
          kindText
          cause {
            links {
              level
              subject
              status
              message
              runId
            }
          }
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
          code
          reason
          kind
          guideTerm
          kindText
          cause {
            links {
              level
              subject
              status
              message
              runId
            }
          }
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
          code
          reason
          kind
          guideTerm
          kindText
          cause {
            links {
              level
              subject
              status
              message
              runId
            }
          }
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
          code
          reason
          kind
          guideTerm
          kindText
          cause {
            links {
              level
              subject
              status
              message
              runId
            }
          }
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

const ResultCosts = graphql(`
  query EdgeResultCosts($id: String!) {
    edgeResult(id: $id) {
      costs {
        state
        variant
        horizon
        assumedBp
        levels {
          period
          bp
          assumed
          sessions
          picks
          winRate
          baseRate
          liftPts
          meanExcess
        }
        periods {
          period
          state
          breakEvenBp
          decileSpread
        }
      }
    }
  }
`);

const ResultCapacity = graphql(`
  query EdgeResultCapacity($id: String!) {
    edgeResult(id: $id) {
      capacity {
        state
        variant
        horizon
        floorUsd
        periods {
          period
          state
          picks
          advMedian
          advKnown
          advLow
        }
      }
    }
  }
`);

const ResultRegimes = graphql(`
  query EdgeResultRegimes($id: String!) {
    edgeResult(id: $id) {
      regimes {
        state
        variant
        horizon
        rows {
          regime
          figures {
            period
            state
            winRate
            baseRate
            liftPts
            trades
            thin
          }
        }
      }
    }
  }
`);

const ResultHorizons = graphql(`
  query EdgeResultHorizons($id: String!) {
    edgeResult(id: $id) {
      horizons {
        state
        variant
        needed
        rows {
          horizon
          basis
          figures {
            period
            state
            winRate
            baseRate
            liftPts
            trades
            thin
          }
          oosBy {
            state
            needed
            have
            remaining
            expectedBy
            fillRatio
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

/** The cost sensitivity of the verdict's basis (null: no such edge). */
export function useEdgeCosts(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultCosts', { id }),
    queryFn: () => gql(ResultCosts, { id }),
    select: (data) => data.edgeResult?.costs ?? null,
  });
}

/** The capacity of the verdict's basis (null: no such edge). */
export function useEdgeCapacity(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultCapacity', { id }),
    queryFn: () => gql(ResultCapacity, { id }),
    select: (data) => data.edgeResult?.capacity ?? null,
  });
}

/** The verdict's basis by market regime (null: no such edge). */
export function useEdgeRegimes(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultRegimes', { id }),
    queryFn: () => gql(ResultRegimes, { id }),
    select: (data) => data.edgeResult?.regimes ?? null,
  });
}

/** The verdict's screen at every holding period (null: no such edge). */
export function useEdgeHorizons(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeResultHorizons', { id }),
    queryFn: () => gql(ResultHorizons, { id }),
    select: (data) => data.edgeResult?.horizons ?? null,
  });
}

/** The variant grid of the edge's official run (null: no such edge). */
export function useEdgeVariants(edgeId: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeVariantGrid', { edgeId }),
    queryFn: () => gql(EdgeVariantGrid, { edgeId }),
    select: (data) => data.edgeVariants,
  });
}
