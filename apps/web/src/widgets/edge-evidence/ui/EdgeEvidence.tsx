/**
 * Section 2 of an edge's page, Evidence: the cumulative curve of the picks against the universe
 * (its own read), the out-of-sample result as a strip and one line, and the figures of both
 * sides of the split side by side. The verdict's own figures come from the edge the page already
 * has; only the curve is fetched here.
 */
import { Heading, Stack } from '@algotrade/ui';

import type { EdgeVerdict } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { EdgeCurve } from './EdgeCurve';
import { EdgeFigures } from './EdgeFigures';
import { EdgeSummary } from './EdgeSummary';

export interface EdgeEvidenceProps {
  edgeId: string;
  verdict: EdgeVerdict;
}

export function EdgeEvidence({ edgeId, verdict }: EdgeEvidenceProps) {
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>Evidence</Heading>
        {termHelp('edge_evidence_section')}
      </Stack>
      <EdgeCurve edgeId={edgeId} />
      <EdgeSummary verdict={verdict} />
      <EdgeFigures verdict={verdict} />
    </Stack>
  );
}
