/**
 * Section 4 of an edge's page, Where it worked: one panel with a view for each way to cut the
 * result, Year by year (the verdict's own rows, from the edge the page has) and Drawdown (its own
 * read, fetched when the view opens).
 */
import { Panel, Tabs, type TabItem } from '@algotrade/ui';
import { useState } from 'react';

import type { EdgeVerdict } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { EdgeDrawdown } from './EdgeDrawdown';
import { EdgeYears } from './EdgeYears';

const VIEWS: TabItem[] = [
  { id: 'years', label: 'Year by year' },
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
      <Tabs items={VIEWS} value={view} onChange={setView} label="Where it worked views">
        {view === 'years' ? <EdgeYears years={verdict.years} /> : <EdgeDrawdown edgeId={edgeId} />}
      </Tabs>
    </Panel>
  );
}
