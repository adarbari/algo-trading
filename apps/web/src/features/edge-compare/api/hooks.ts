/**
 * The comparison of the user's copy `id` (`Query.edge(id).compare`). Keyed under `EdgesPage` so
 * every refresh of the edges (a run finished, a state changed, the out-of-sample shown) reads it
 * again.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, queryKeys, TypedDocumentString } from '@/shared/api';

export interface CompareFigures {
  winRate: number | null;
  baseRate: number | null;
  liftPts: number | null;
  trades: number | null;
}

export interface CompareRow {
  label: string;
  basis: string;
  inSample: CompareFigures | null;
  outOfSample: CompareFigures | null;
}

export interface EdgeCompareResult {
  oosHidden: boolean;
  reason: string;
  rows: CompareRow[];
}

const FIGURES = 'winRate baseRate liftPts trades';
const Document = new TypedDocumentString<
  { edge: { compare: EdgeCompareResult | null } | null },
  { id: string }
>(`query EdgeCompare($id: String!) { edge(id: $id) { compare {
  oosHidden reason rows { label basis inSample { ${FIGURES} } outOfSample { ${FIGURES} } } } } }`);

export function useEdgeCompare(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('EdgesPage', { compare: id }),
    queryFn: () => gql(Document, { id }),
    select: (data) => data.edge?.compare ?? null,
  });
}
