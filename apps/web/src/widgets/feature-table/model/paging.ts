/**
 * The page a server-paged table shows: it belongs to the query, so any other query (columns,
 * filters, sort) starts on its first page.
 */
import { useState } from 'react';

/** `[page, setPage]` for the query described by `shape` (any JSON of what it asks). */
export function usePageOf(shape: string): [number, (page: number) => void] {
  const [paging, setPaging] = useState({ shape, page: 1 });
  const page = paging.shape === shape ? paging.page : 1;
  return [
    page,
    (next) => {
      setPaging({ shape, page: next });
    },
  ];
}
