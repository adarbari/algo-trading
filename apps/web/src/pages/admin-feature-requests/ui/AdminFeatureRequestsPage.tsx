/**
 * Admin > Feature requests: the features traders asked Describe it for that the catalogue does
 * not have, ranked by the server (distinct users, recency, feasibility), counts only. The page
 * only lays the widget out.
 */
import { Heading, Stack } from '@algotrade/ui';

import { FeatureRequestList } from '@/widgets/feature-request-list';

export function AdminFeatureRequestsPage() {
  return (
    <Stack gap={4}>
      <Heading level={1}>Feature requests</Heading>
      <FeatureRequestList />
    </Stack>
  );
}
