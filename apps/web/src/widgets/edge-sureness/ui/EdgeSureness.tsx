/**
 * Section 3 of an edge's page, How sure: the decile staircase, the robustness against random
 * picks with the multiple-testing line, and the decay of the number from the paper to the live
 * record, side by side (stacked on a narrow screen). The verdict's figures come from the edge
 * the page already has; only the decay is fetched here.
 */
import { Grid, Heading, Stack } from '@algotrade/ui';

import type { EdgeVerdict } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { EdgeDecay } from './EdgeDecay';
import { EdgeDeciles } from './EdgeDeciles';
import { EdgeRobustness } from './EdgeRobustness';

export interface EdgeSurenessProps {
  edgeId: string;
  verdict: EdgeVerdict;
}

export function EdgeSureness({ edgeId, verdict }: EdgeSurenessProps) {
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>How sure</Heading>
        {termHelp('edge_how_sure')}
      </Stack>
      <Grid columns={3} gap={4} collapse="lg" align="start">
        <EdgeDeciles deciles={verdict.deciles} />
        <EdgeRobustness verdict={verdict} />
        <EdgeDecay edgeId={edgeId} />
      </Grid>
    </Stack>
  );
}
