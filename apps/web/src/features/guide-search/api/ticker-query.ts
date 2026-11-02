/**
 * The ticker search's read (the feature table with no columns: the matching instruments only) and
 * the dialog group built from it, in a module of its own so it loads with the first search.
 */
import type { SearchDialogGroup } from '@algotrade/ui';

import { fetchFeatureTable } from '@/entities/feature';

/** The Tickers group for `q`: each result opens the ticker in Explore; empty when none match. */
export async function tickerGroups(q: string, size: number): Promise<SearchDialogGroup[]> {
  const found = (await fetchFeatureTable({ columns: [], q, size }))?.rows ?? [];
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
