/**
 * The edges pages' one read (ADR 0037 / 0053, ED8): `Query.edges`, each edge document with its
 * verdict (judged by the read model on the official result, the canonical run: the sentence, the
 * figures, the criteria and the year rows), how it is defined, its sources, and every run the
 * user sees so exploratory ones can be listed and labelled. The cache holds the response.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const EdgesPage = graphql(`
  query EdgesPage {
    edges {
      id
      name
      status
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
          winRate
          baseRate
          liftPts
          decileSpread
          trades
        }
      }
      canonicalRun {
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

/** Every edge the user sees (empty: none declared). */
export function useEdges() {
  return useQuery({ ...edgesQuery(), select: (data) => data.edges });
}

const edgesQuery = () =>
  queryOptions({
    queryKey: queryKeys.gql('EdgesPage', {}),
    queryFn: () => gql(EdgesPage, {}),
  });

/** Start reading the edges before the page opens (a link was hovered): a no-op while fresh. */
export function prefetchEdges(client: QueryClient): void {
  void client.prefetchQuery(edgesQuery());
}

/** Read the edges (and their runs) again, after an evaluation finished. */
export function refreshEdges(client: QueryClient): Promise<void> {
  return client.invalidateQueries({ queryKey: queryKeys.gqlAll('EdgesPage') });
}
