/** Page: Admin › Harness runs (the evaluation runs and one run's rows). */
import { prefetchHarnessRuns } from '@/entities/harness-run';

export { AdminHarnessRunsPage, type AdminHarnessRunsPageProps } from './ui/AdminHarnessRunsPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchHarnessRunsReads(client: Parameters<typeof prefetchHarnessRuns>[0]): void {
  prefetchHarnessRuns(client);
}
