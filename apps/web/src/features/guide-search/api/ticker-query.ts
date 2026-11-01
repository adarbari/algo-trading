/**
 * The ticker search's read (`Query.table` with no columns: the matching instruments only) and the
 * dialog group built from it, in a module of its own so it loads with the first search.
 */
import type { SearchDialogGroup } from '@algotrade/ui';

import { gql, graphql } from '@/shared/api';

const TickerSearchQuery = graphql(`
  query TickerSearch($q: String!, $size: Int!) {
    table(columns: [], q: $q, size: $size) {
      instruments {
        instrumentId
        symbol
        name
      }
    }
  }
`);

/** The Tickers group for `q`: each result opens the ticker in Explore; empty when none match. */
export async function tickerGroups(
  variables: { q: string; size: number },
  queryKey: readonly unknown[],
): Promise<SearchDialogGroup[]> {
  const found = (await gql(TickerSearchQuery, variables, queryKey)).table?.instruments ?? [];
  if (found.length === 0) return [];
  return [
    {
      id: 'ticker',
      title: 'Tickers',
      items: found.map(({ symbol, name }) => ({
        id: symbol,
        title: symbol,
        snippet: name,
        href: `/explore?sel=${encodeURIComponent(symbol)}&focus=${encodeURIComponent(symbol)}`,
      })),
    },
  ];
}
