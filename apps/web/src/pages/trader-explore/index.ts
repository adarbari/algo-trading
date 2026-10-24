/** Page: Trader > Explore (ticker table, compare, chart, options, features, events). */
import { prefetchFilterSet } from '@/entities/filter';
import { prefetchScreenerHits } from '@/entities/screen';

import type { ExploreSearch } from '@/entities/explore';
import { exploreState } from './model/state';
import { preloadOtherTabs } from './ui/DetailTabs';
import { preloadUniverseTable } from './ui/ExplorePage';

export { type SearchPatch } from './model/state';
export { ExplorePage, type ExplorePageProps } from './ui/ExplorePage';

/**
 * Start the reads of the tab the URL opens on (the route's loader), so they run beside the
 * tab's chunk instead of after it mounts; the widgets' hooks join them. Overview and Chart are
 * in the page, so only the other tabs load a chunk. Resolves when that chunk is loaded (never
 * waits for data).
 */
export function prefetchExploreReads(
  client: Parameters<typeof prefetchScreenerHits>[0],
  search: ExploreSearch,
): Promise<void> {
  const { tab, focused } = exploreState(search);
  // no ticker open: the universe table's filter definitions load with the page
  if (!focused) {
    prefetchFilterSet(client, 'universe');
    return preloadUniverseTable();
  }
  if (tab === 'overview' || tab === 'chart') return Promise.resolve();
  if (focused && (tab === 'hits' || tab === 'why')) prefetchScreenerHits(client, focused);
  if (focused && tab === 'features') {
    // a dynamic import: the panel's code stays in the tabs' chunk, not in this page's
    void import('@/widgets/features-panel').then((m) => m.prefetchFeaturesReads(client, focused));
  }
  return preloadOtherTabs();
}
