/**
 * The edges page's one read (ADR 0037 / 0053): `Query.edges`, each edge document with its
 * canonical run (the latest site run whose split is the frozen period, never an exploratory one)
 * and its stored rows, plus every run the user sees (without rows) so exploratory ones can be
 * listed and labelled. The cache holds the response; `select` shapes it.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { toEdges } from '../model/edges';

const EdgesPage = graphql(`
  query EdgesPage {
    edges {
      id
      name
      status
      thesis
      mechanism
      persistence
      schedule
      horizons
      screeners
      baselines
      variants
      frozenFrom
      rejectionReason
      evidence {
        runId
        splitFrom
      }
      canonicalRun {
        runId
        owner
        rangeFrom
        rangeTo
        splitFrom
        exploratory
        knowledgeTs
        afterSession
        rows {
          edgeVariant
          variant
          role
          horizonSessions
          sliceKind
          sliceValue
          sessions
          picks
          hitRate
          baseRate
          lift
          exploratory
        }
      }
      canonicalNotRun {
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
      runs {
        runId
        owner
        rangeFrom
        rangeTo
        splitFrom
        exploratory
        knowledgeTs
      }
    }
  }
`);

/** Every edge the user sees (empty: none declared). */
export function useEdges() {
  return useQuery({
    queryKey: queryKeys.gql('EdgesPage', {}),
    queryFn: () => gql(EdgesPage, {}),
    select: toEdges,
  });
}
