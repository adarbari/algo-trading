/**
 * Admin > Feature requests: the features traders asked Describe it for that the catalogue does
 * not have, ranked by the server (distinct users, recency, feasibility), counts only, then the
 * formulas traders accepted, grouped by the server. The chosen
 * status comes from the route (shareable); the page only lays the widget out.
 */
import { Heading, Skeleton, Stack } from '@algotrade/ui';
import { lazy, Suspense } from 'react';

import { FeatureRequestList } from '@/widgets/feature-request-list';

const AcceptedFormulasSection = lazy(() => import('./AcceptedFormulasSection'));

export interface AdminFeatureRequestsPageProps {
  /** The status shown (from the URL); null or absent: every status. */
  status?: string | null;
  onStatusChange: (status: string | null) => void;
}

export function AdminFeatureRequestsPage({
  status = null,
  onStatusChange,
}: AdminFeatureRequestsPageProps) {
  return (
    <Stack gap={4}>
      <Heading level={1}>Feature requests</Heading>
      <FeatureRequestList status={status} onStatusChange={onStatusChange} />
      <Suspense
        fallback={
          <Skeleton variant="table" rows={4} columns={4} label="Loading accepted formulas…" />
        }
      >
        <AcceptedFormulasSection />
      </Suspense>
    </Stack>
  );
}
