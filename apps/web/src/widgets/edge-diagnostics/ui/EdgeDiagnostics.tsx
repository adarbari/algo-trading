/**
 * The deeper figures of an edge's Details: the variant grid (every screen and holding period the
 * run tried), the rolling starts, the capacity of the picks and the monthly map. Each is its own
 * read in its own `LazySection`, loaded when it nears the viewport; the page puts this inside the
 * Details disclosure, so nothing is read until the user opens it.
 */
import { Grid, Heading, LazySection, Stack } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { termHelp } from '@/features/guide-help';

import { EdgeCapacity } from './EdgeCapacity';
import { EdgeMonthly } from './EdgeMonthly';
import { EdgeRollingStarts } from './EdgeRollingStarts';
import { EdgeVariants } from './EdgeVariants';

function Subsection({
  title,
  term,
  children,
}: {
  title: string;
  term: string;
  children: ReactNode;
}) {
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={3}>{title}</Heading>
        {termHelp(term)}
      </Stack>
      <LazySection label={title} minBlockSize="md">
        {children}
      </LazySection>
    </Stack>
  );
}

export interface EdgeDiagnosticsProps {
  edgeId: string;
}

export function EdgeDiagnostics({ edgeId }: EdgeDiagnosticsProps) {
  return (
    <Stack gap={4}>
      <Subsection title="Variants tried" term="variant_grid">
        <EdgeVariants edgeId={edgeId} />
      </Subsection>
      <Grid columns={2} gap={4} collapse="md" align="start">
        <Subsection title="Rolling starts" term="rolling_starts">
          <EdgeRollingStarts edgeId={edgeId} />
        </Subsection>
        <Subsection title="Capacity" term="capacity">
          <EdgeCapacity edgeId={edgeId} />
        </Subsection>
      </Grid>
      <Subsection title="Monthly map" term="monthly_map">
        <EdgeMonthly edgeId={edgeId} />
      </Subsection>
    </Stack>
  );
}
