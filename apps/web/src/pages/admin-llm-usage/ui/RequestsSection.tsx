/**
 * What traders asked for and the catalogue lacks, then the formulas they accepted: the Feature
 * requests widgets inside the AI view, in one lazy chunk (nothing here paints before a trader
 * opens the Requests view). The status filter is the view's own state.
 */
import { useState } from 'react';

import { Stack } from '@algotrade/ui';

import { AcceptedFormulaList } from '@/widgets/accepted-formula-list';
import { FeatureRequestList } from '@/widgets/feature-request-list';

export default function RequestsSection() {
  const [status, setStatus] = useState<string | null>(null);
  return (
    <Stack gap={4}>
      <FeatureRequestList status={status} onStatusChange={setStatus} />
      <AcceptedFormulaList />
    </Stack>
  );
}
