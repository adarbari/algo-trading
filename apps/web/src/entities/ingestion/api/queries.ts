/**
 * Read hooks for ingestion completeness over GraphQL (`Query.{completeness,ingestionCell}`;
 * ADR 0037): the grid (the window of sessions ending at the latest) and one cell's drill-down.
 */
import { useQuery } from '@tanstack/react-query';

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

/** The grid; null: nothing stored. */
export function useCompleteness(sessions = SESSIONS) {
  return useQuery({
    queryKey: queryKeys.gql('IngestionCompleteness', { sessions }),
    queryFn: () => gql(IngestionCompleteness, { sessions }),
    select: (data) => data.completeness,
  });
}

/** One cell with the reasons behind it; null: a dataset the grid does not list. */
export function useCellDetail(cell: CellRef | null) {
  const variables = { dataset: cell?.dataset ?? '', date: cell?.session ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('IngestionCell', variables),
    queryFn: () => gql(IngestionCell, variables),
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
