/**
 * Read hooks for ingestion completeness over GraphQL (`Query.{completeness,ingestionCell}`;
 * ADR 0037): the grid (the window of sessions ending at the latest), one cell's drill-down and
 * the option-chain coverage of the session (`Query.chainCoverage`, read with the grid: one request).
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { defaultCell, SESSIONS } from '../model/grid';
import type { CellRef } from '../model/types';

const IngestionCompleteness = graphql(`
  query IngestionCompleteness($sessions: Int!) {
    completeness(sessions: $sessions) {
      sessions
      datasets
      lastClosed
      cells {
        dataset
        session
        status
        present
        expected
        basis
        runIds
      }
    }
    chainCoverage {
      session
      total
      ok
      share
      statuses {
        code
        count
      }
      tiers {
        tier
        total
        ok
        stale
      }
      chronic
      chronicNames
      previousChronic
      drift
    }
    knownCoverage {
      session
      runId
      byType {
        securityType
        names
        rows
        known
        share
      }
      gaps {
        gap
        names
      }
      unknown {
        code
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
`);

const IngestionCell = graphql(`
  query IngestionCell($dataset: String!, $date: Date!) {
    ingestionCell(dataset: $dataset, date: $date) {
      job
      cell {
        dataset
        session
        status
        present
        expected
        basis
        runIds
      }
      groups {
        reason
        count
        examples
        statuses
      }
      runs {
        runId
        job
        session
        status
        startedAt
        finishedAt
        durationS
        itemsTotal
        itemsByStatus
        stats
        failures {
          reason
          count
          examples
          statuses
        }
      }
    }
  }
`);

/** The option-chain coverage of the served session (rides the grid's read); null: no chains run. */
export function useChainCoverage() {
  const sessions = SESSIONS;
  return useQuery({
    ...completenessQuery(sessions),
    select: (data) => data.chainCoverage,
  });
}

function completenessQuery(sessions = SESSIONS) {
  return queryOptions({
    queryKey: queryKeys.gql('IngestionCompleteness', { sessions }),
    queryFn: ({ queryKey }) => gql(IngestionCompleteness, { sessions }, queryKey),
  });
}

/** Start the grid's read before the page mounts (a route loader); the hooks then join it. */
export function prefetchCompleteness(client: QueryClient, sessions = SESSIONS): void {
  void client.query(completenessQuery(sessions)).catch(() => undefined);
}

/** The fundamentals share count known against rows stored (rides the grid's read); null: nothing stored. */
export function useKnownCoverage() {
  return useQuery({
    ...completenessQuery(SESSIONS),
    select: (data) => data.knownCoverage,
  });
}

/** The grid; null: nothing stored. */
export function useCompleteness(sessions = SESSIONS, enabled = true) {
  return useQuery({
    ...completenessQuery(sessions),
    enabled,
    select: (data) => data.completeness,
  });
}

/** One cell with the reasons behind it; null: a dataset the grid does not list. */
export function useCellDetail(cell: CellRef | null) {
  const variables = { dataset: cell?.dataset ?? '', date: cell?.session ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('IngestionCell', variables),
    queryFn: ({ queryKey }) => gql(IngestionCell, variables, queryKey),
    select: (data) => data.ingestionCell,
    enabled: cell !== null,
  });
}

/** The cell in focus: the selected one, else the grid's default (once the grid has loaded). */
export function useFocusCell(selected: CellRef | null | undefined): CellRef | null {
  const { data } = useCompleteness();
  if (selected) return selected;
  return data ? defaultCell(data) : null;
}
