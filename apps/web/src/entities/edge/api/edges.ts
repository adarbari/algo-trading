/**
 * The edges pages' reads (ADR 0037 / 0053, ED8). The list (`EdgesPage`): `Query.edges` with each
 * edge's row and `summary` (the headline of its verdict: label, result, trades) and the user's own
 * files that did not load (`Query.edgeProblems`); no verdict is judged in full for it. One edge
 * (`EdgeDetail`): the edge in full, the verdict (judged by the read model on the official result,
 * the canonical run: the sentence, the figures, the criteria, the year rows, the in-sample decile
 * means and the lift among random-pick backtests, and the provenance line: which evaluation it rests on and whether it is current), how it is defined, its sources, and every run
 * the user sees so exploratory ones can be listed and labelled. The cache holds the responses.
 */
import { keepPreviousData, queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { toFilterInputs, type AppliedFilter, type FilterInput } from '@/entities/filter';
import { gql, graphql, queryKeys } from '@/shared/api';

const EdgesPage = graphql(`
  query EdgesPage($filters: [FilterInput!], $q: String) {
    edgeList(filters: $filters, q: $q) {
      total
      facets {
        total
        matched
        items {
          id
          active
          removes
          unknown
          options {
            value
            count
          }
          bins {
            lo
            hi
            count
          }
        }
      }
      items {
        id
        name
        thesis
        status
        state
        mine
        screeners
        summary {
          verdict
          result
          trades
        }
      }
    }
  }
`);

const EdgeProblems = graphql(`
  query EdgeProblems {
    edgeProblems {
      edgeId
      reason
    }
  }
`);

/**
 * One edge in full (`?edge=X`): the whole verdict, the definition and every run the user sees,
 * for ONE edge, so the server judges one verdict, not every edge's.
 */
const EdgeDetail = graphql(`
  query EdgeDetail($ids: [String!]!) {
    edges(ids: $ids) {
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
      provenance {
        state
        line
        runId
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
      variantsTried
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

/**
 * The edges the user sees that pass `applied` and match `q` (over name and thesis), as list rows
 * with the headline of each verdict only, and the filter bar's counts (`facets`: `total` is the
 * count before the filters, 0 when none is declared). The last list stays while new filters load.
 */
export function useEdges(applied: readonly AppliedFilter[] = NO_FILTERS, q = '') {
  const filters = useMemo(() => toFilterInputs(applied), [applied]);
  return useQuery({
    ...edgesQuery(filters, q),
    placeholderData: keepPreviousData,
    select: (data) => data.edgeList,
  });
}
const NO_FILTERS: readonly AppliedFilter[] = [];

/** One edge in full (null id: nothing is read); `data` is the edge, or null when it is not seen. */
export function useEdge(id: string | null) {
  return useQuery({
    ...edgeQuery(id ?? ''),
    enabled: id !== null,
    select: (d) => d.edges[0] ?? null,
  });
}

const edgeQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.gql('EdgeDetail', { ids: [id] }),
    queryFn: ({ queryKey }) => gql(EdgeDetail, { ids: [id] }, queryKey),
  });

/** Start reading one edge before its page opens (the URL names it): a no-op while fresh. */
export function prefetchEdge(client: QueryClient, id: string): void {
  void client.query(edgeQuery(id)).catch(() => undefined);
}

/** The user's own edge files that did not load, each with its reason (empty: all load). */
export function useEdgeProblems() {
  return useQuery({
    queryKey: queryKeys.gql('EdgeProblems', {}),
    queryFn: ({ queryKey }) => gql(EdgeProblems, {}, queryKey),
    select: (data) => data.edgeProblems,
  });
}

const edgesQuery = (filters: readonly FilterInput[] | null, q: string) => {
  const variables = { ...(filters && { filters: [...filters] }), ...(q && { q }) };
  return queryOptions({
    queryKey: queryKeys.gql('EdgesPage', variables),
    queryFn: ({ queryKey }) =>
      gql(EdgesPage, { filters: variables.filters ?? null, q: variables.q ?? null }, queryKey),
  });
};

/** Start reading the edges before the page opens (a link was hovered): a no-op while fresh. */
export function prefetchEdges(
  client: QueryClient,
  applied: readonly AppliedFilter[] = NO_FILTERS,
  q = '',
): void {
  void client.query(edgesQuery(toFilterInputs(applied), q)).catch(() => undefined);
  void client
    .query({
      queryKey: queryKeys.gql('EdgeProblems', {}),
      queryFn: ({ queryKey }) => gql(EdgeProblems, {}, queryKey),
    })
    .catch(() => undefined);
}

/** Read the edges (and their runs) again, after an evaluation finished. */
export function refreshEdges(client: QueryClient): Promise<void> {
  return Promise.all(
    ['EdgeDocument', 'EdgeDetail', 'EdgesPage', 'EdgeProblems'].map((name) =>
      client.invalidateQueries({ queryKey: queryKeys.gqlAll(name) }),
    ),
  ).then(() => undefined);
}
