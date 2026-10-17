/** Page: Admin › Ingestion (completeness, drill-down, quality, verification, runs). */
import { prefetchCompleteness } from '@/entities/ingestion';
import { prefetchFigiReview, prefetchLeveragedReview } from '@/entities/review';
import { prefetchNightlyRuns, prefetchQualityChecks } from '@/entities/run';
import { prefetchVerification } from '@/entities/verification';

export { AdminIngestionPage, type AdminIngestionPageProps } from './ui/AdminIngestionPage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchIngestionReads(client: Parameters<typeof prefetchCompleteness>[0]): void {
  prefetchCompleteness(client);
  prefetchNightlyRuns(client);
  prefetchQualityChecks(client);
  prefetchFigiReview(client);
  prefetchLeveragedReview(client);
  prefetchVerification(client);
}
