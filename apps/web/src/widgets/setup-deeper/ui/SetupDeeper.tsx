/**
 * "Dig deeper" on a setup's page, behind one Disclosure: how sure (the decile staircase, the
 * robustness against random picks with the multiple-testing line, the decay of the number from
 * the paper to the live record), then the verdict's tests and the backtests, and the sections the
 * page composes in (a copy's comparison, the trades, the diagnostics). The body loads on first
 * open, so the page's first paint stays small.
 */
import { Disclosure, Grid, Heading, Stack } from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import type { Edge } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { EdgeCompare } from './EdgeCompare';
import { EdgeDecay } from './EdgeDecay';
import { EdgeDeciles } from './EdgeDeciles';
import { EdgeDetailsBody } from './EdgeDetailsBody';
import { EdgeRobustness } from './EdgeRobustness';

export interface SetupDeeperProps {
  edge: Edge;
  /** More sections (the page composes them), shown with the body once opened. */
  children?: ReactNode;
}

export function SetupDeeper({ edge, children }: SetupDeeperProps) {
  const [open, setOpen] = useState(false);
  return (
    <Disclosure
      label="Dig deeper"
      count={String(edge.verdict.criteria.length)}
      open={open}
      onOpenChange={setOpen}
    >
      {open && (
        <Stack gap={4}>
          <Stack gap={3}>
            <Stack direction="row" gap={1} align="center">
              <Heading level={3}>How sure</Heading>
              {termHelp('edge_how_sure')}
            </Stack>
            <Grid columns={3} gap={4} collapse="lg" align="start">
              <EdgeDeciles deciles={edge.verdict.deciles} />
              <EdgeRobustness verdict={edge.verdict} />
              <EdgeDecay edgeId={edge.id} />
            </Grid>
          </Stack>
          <EdgeDetailsBody edge={edge} />
          {edge.mine && <EdgeCompare edgeId={edge.id} />}
          {children}
        </Stack>
      )}
    </Disclosure>
  );
}
