/** Page: Admin › Screener runs (every run of any status and one run's record). */
import { prefetchScreenerRuns, type ScreenerRunFilters } from '@/entities/screener-run';

export {
  AdminScreenerRunsPage,
  readSearch,
  type AdminScreenerRunsPageProps,
} from './ui/AdminScreenerRunsPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchScreenerRunsReads(
  client: Parameters<typeof prefetchScreenerRuns>[0],
  filters: ScreenerRunFilters = {},
): void {
  prefetchScreenerRuns(client, filters);
}
