/**
 * The edges pages' one read (ADR 0037 / 0053, ED8): `Query.edges` (and the user's own files that
 * did not load, `Query.edgeProblems`), each edge document with the user's state about it; the
 * verdict (judged by the read model on the official result, the canonical run: the sentence, the
 * figures, the criteria, the year rows, the in-sample decile means and the lift among random-pick
 * backtests), whether it is the user's own, how it is defined, its sources, and every run the
 * user sees so exploratory ones can be listed and labelled. The cache holds the response.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const EdgesPage = graphql(`
  query EdgesPage {
    edgeProblems {
      edgeId
      reason
    }
    edges {
      id
      name
      status
      state
      labels
      oosHidden
      mine
      extends
      thesis
      mechanism
      persistence
      horizons
      screeners
      baselines
      rejectionReason
      sources {
        title
        url
      }
      definition {
        picks
        trade
        compare
        test
      }
      verdict {
        verdict
        rationale
        headline
        result
        basis
        basisWhy
        side
        trades
        oosTrades
        winRate
        baseRate
        liftPts
        lift
        decileSpread
        decileT
        sharpe
        deflatedSharpe
        pbo
        trials
        deciles
        robustness {
          lift
          draws
          beats
          summary
          bins {
            start
            end
            count
          }
        }
        criteria {
          id
          label
          value
          threshold
          status
          level
        }
        years {
          year
          period
          label
          fromDate
          toDate
          partial
          winRate
          baseRate
          liftPts
          decileSpread
          trades
        }
        columns {
          period
          winRate
          baseRate
          liftPts
          trades
          decileSpread
          decileT
          sharpe
          deflatedSharpe
          pbo
          thin
          referenceRate
          touchRate
        }
        evidence {
          oosTrades
          needed
          worksOosNeeded
          wholeTrades
          wholeNeeded
          reached
          checks {
            id
            label
            value
            threshold
            status
            level
          }
          outlook {
            criterion
            level
            sentence
            have
            needed
            remaining
            projectionState
            expectedBy
            fillRatio
            cadenceSessions
            nextClose
            projections {
              criterion
              oos
              have
              needed
              remaining
              state
              expectedBy
              fillRatio
              cadenceSessions
            }
            atTarget {
              needed
              level
              reasons
              sentence
            }
          }
        }
        haircut {
          sharpe
          haircutSharpe
          cut
          trials
          sessions
          method
          summary
        }
        decay {
          measure
          unit
          basisHorizon
          published {
            measure
            value
            horizonSessions
            source {
              title
              url
            }
            sample
          }
          bars {
            period
            value
            n
            state
          }
        }
      }
      canonicalRun {
        runId
        knowledgeTs
      }
      runs {
        runId
        owner
        rangeFrom
        rangeTo
        splitFrom
        exploratory
        knowledgeTs
        trialsCounted
        lostInputs
      }
    }
  }
`);

/**
 * One edge's document, for the builder (`/edges/:id/edit`): what it needs to start a draft and
 * nothing the harness judges: no verdict, no runs, so the server reads neither.
 */
const EdgeDocument = graphql(`
  query EdgeDocument($ids: [String!]!) {
    edges(ids: $ids) {
      id
      name
      state
      mine
      extends
      thesis
      mechanism
      persistence
      horizons
      screeners
      baselines
      sources {
        title
        url
      }
      definition {
        picks
        trade
        compare
        test
      }
    }
  }
`);

/** One edge's document (null id: nothing is read; `data` is then the empty list's `undefined`). */
export function useEdgeDocument(id: string | null) {
  return useQuery({
    queryKey: queryKeys.gql('EdgeDocument', { ids: [id ?? ''] }),
    queryFn: ({ queryKey }) => gql(EdgeDocument, { ids: [id ?? ''] }, queryKey),
    enabled: id !== null,
    select: (data) => data.edges[0] ?? null,
  });
}

/** Every edge the user sees (empty: none declared). */
export function useEdges() {
  return useQuery({ ...edgesQuery(), select: (data) => data.edges });
}

/** The user's own edge files that did not load, each with its reason (empty: all load). */
export function useEdgeProblems() {
  return useQuery({ ...edgesQuery(), select: (data) => data.edgeProblems });
}

const edgesQuery = () =>
  queryOptions({
    queryKey: queryKeys.gql('EdgesPage', {}),
    queryFn: ({ queryKey }) => gql(EdgesPage, {}, queryKey),
  });

/** Start reading the edges before the page opens (a link was hovered): a no-op while fresh. */
export function prefetchEdges(client: QueryClient): void {
  void client.query(edgesQuery()).catch(() => undefined);
}

/** Read the edges (and their runs) again, after an evaluation finished. */
export function refreshEdges(client: QueryClient): Promise<void> {
  void client.invalidateQueries({ queryKey: queryKeys.gqlAll('EdgeDocument') });
  return client.invalidateQueries({ queryKey: queryKeys.gqlAll('EdgesPage') });
}
