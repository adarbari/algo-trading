/**
 * Section 4 of an edge's page, Where it worked: one panel with a view for each way to cut the
 * result, Year by year (the verdict's own rows, from the edge the page has), Regime, Holding period
 * and Drawdown (each its own read, fetched when the view opens), and under them the cost
 * sensitivity of the verdict's basis.
 */
import { Divider, Panel, Stack, Tabs, type TabItem } from '@algotrade/ui';
import { useState } from 'react';

import type { EdgeVerdict } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { EdgeCosts } from './EdgeCosts';
import { EdgeDrawdown } from './EdgeDrawdown';
import { EdgeHorizons } from './EdgeHorizons';
import { EdgeRegimes } from './EdgeRegimes';
import { EdgeYears } from './EdgeYears';

const VIEWS: TabItem[] = [
  { id: 'years', label: 'Year by year' },
  { id: 'regime', label: 'Regime' },
  { id: 'horizon', label: 'Holding period' },
  { id: 'drawdown', label: 'Drawdown' },
];

export interface EdgePerformanceProps {
  edgeId: string;
  verdict: EdgeVerdict;
}

export function EdgePerformance({ edgeId, verdict }: EdgePerformanceProps) {
  const [view, setView] = useState('years');
  return (
    <Panel title="Where it worked" headingLevel={2} actions={termHelp('edge_where_worked')}>
      <Stack gap={3}>
        <Tabs items={VIEWS} value={view} onChange={setView} label="Where it worked views">
          {view === 'years' && <EdgeYears years={verdict.years} />}
          {view === 'regime' && <EdgeRegimes edgeId={edgeId} />}
          {view === 'horizon' && <EdgeHorizons edgeId={edgeId} />}
          {view === 'drawdown' && <EdgeDrawdown edgeId={edgeId} />}
        </Tabs>
        <Divider />
        <EdgeCosts edgeId={edgeId} />
      </Stack>
    </Panel>
  );
}
