/**
 * Admin > Feature requests: the features traders asked Describe it for that the catalogue does
 * not have, ranked by the server (distinct users, recency, feasibility), counts only. The chosen
 * status comes from the route (shareable); the page only lays the widget out.
 */
import { Heading, Stack } from '@algotrade/ui';

import { FeatureRequestList } from '@/widgets/feature-request-list';

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
    </Stack>
  );
}
