/** Read hooks for ingestion completeness: the grid and one cell's drill-down. */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

import { defaultCell, SESSIONS } from '../model/grid';
import type { CellRef } from '../model/types';

export function useCompleteness(sessions = SESSIONS) {
  return useQuery({
    queryKey: queryKeys.admin.completeness(sessions),
    queryFn: () =>
      unwrap(api.GET('/admin/ingestion/completeness', { params: { query: { sessions } } })),
  });
}

export function useCellDetail(cell: CellRef | null) {
  return useQuery({
    queryKey: queryKeys.admin.cell(cell?.dataset ?? '', cell?.session ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/admin/ingestion/{dataset}/{session}', {
          params: { path: { dataset: cell?.dataset ?? '', session: cell?.session ?? '' } },
        }),
      ),
    enabled: cell !== null,
  });
}

/** The cell in focus: the selected one, else the grid's default (once the grid has loaded). */
export function useFocusCell(selected: CellRef | null | undefined): CellRef | null {
  const { data } = useCompleteness();
  if (selected) return selected;
  return data ? defaultCell(data) : null;
}
