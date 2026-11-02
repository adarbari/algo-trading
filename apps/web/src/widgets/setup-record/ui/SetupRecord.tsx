/**
 * Section "How it has done" of a setup's page: the out-of-sample result as an evidence strip
 * (labelled backtested, hypothetical) and one line, the cumulative curve, and under disclosures
 * the year by year, the drawdown and cost sensitivity, the figures of both sides of the split and
 * the forward paper record. The verdict's own figures come from the setup the page already has;
 * the curve and the disclosures read their own numbers when opened.
 */
import { Disclosure, Heading, Stack } from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import type { EdgeVerdict, LiveState } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { EdgeCosts } from './EdgeCosts';
import { EdgeCurve } from './EdgeCurve';
import { EdgeDrawdown } from './EdgeDrawdown';
import { EdgeFigures } from './EdgeFigures';
import { EdgeLive } from './EdgeLive';
import { EdgeSummary } from './EdgeSummary';
import { EdgeYears } from './EdgeYears';

export interface SetupRecordProps {
  edgeId: string;
  verdict: EdgeVerdict;
  /** The setup's live state for the session (the forward record always shows: a record or why none). */
  live: LiveState | undefined;
}

/** A disclosure that mounts its body on first open, so its read waits for the reader. */
function Opened({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Disclosure label={label} open={open} onOpenChange={setOpen}>
      {open && children}
    </Disclosure>
  );
}

export function SetupRecord({ edgeId, verdict, live }: SetupRecordProps) {
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>How it has done</Heading>
        {termHelp('setup_how_done')}
      </Stack>
      <EdgeSummary verdict={verdict} />
      <EdgeCurve edgeId={edgeId} />
      <Opened label="Year by year">
        <EdgeYears years={verdict.years} />
      </Opened>
      <Opened label="Drawdown and costs">
        <Stack gap={3}>
          <EdgeDrawdown edgeId={edgeId} />
          <EdgeCosts edgeId={edgeId} />
        </Stack>
      </Opened>
      <Opened label="Figures of both sides of the split">
        <EdgeFigures verdict={verdict} />
      </Opened>
      <EdgeLive edgeId={edgeId} live={live} />
    </Stack>
  );
}
