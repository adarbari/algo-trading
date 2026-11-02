/**
 * Admin › AI and requests: what the text model spends, so the cost never blows up, and what
 * traders asked for that the catalogue lacks. Three views under the page heading: Overview (spend
 * by window against the budget caps, the last 30 days by day, where it goes, fallbacks and
 * failures), Calls (the latest calls beside the chosen call's detail) and Requests (the ranked
 * feature requests and the accepted formulas). The chosen call comes from the route (shareable)
 * and opens the Calls view; the page only lays the widgets out.
 */
import { Grid, Heading, Skeleton, Stack, Tabs } from '@algotrade/ui';
import { lazy, Suspense, useState } from 'react';

import { UsageBreakdownPanel } from '@/widgets/usage-breakdown-panel';
import { UsageBudgetPanel } from '@/widgets/usage-budget-panel';
import { UsageReliabilityPanel } from '@/widgets/usage-reliability-panel';
import { UsageTrendPanel } from '@/widgets/usage-trend-panel';

// One lazy chunk for the calls list and its detail, one for the requests (each lazy import adds
// a dependency list to the page chunk, so there are two, not one per widget).
const CallsSection = lazy(() => import('./CallsSection'));
const RequestsSection = lazy(() => import('./RequestsSection'));

const VIEWS = [
  { id: 'overview', label: 'Overview' },
  { id: 'calls', label: 'Calls' },
  { id: 'requests', label: 'Requests' },
] as const;

type View = (typeof VIEWS)[number]['id'];

export interface AdminLlmUsagePageProps {
  /** The chosen call (from the URL), if any. */
  selected?: string | null;
  onSelectCall: (id: string) => void;
  /** Narrow only: the detail sheet was dismissed; the route clears the call. */
  onClearCall: () => void;
}

export function AdminLlmUsagePage({
  selected = null,
  onSelectCall,
  onClearCall,
}: AdminLlmUsagePageProps) {
  const [chosen, setView] = useState<View | null>(null);
  const view: View = chosen ?? (selected ? 'calls' : 'overview');
  return (
    <Stack gap={4}>
      <Heading level={1}>AI and requests</Heading>
      <Tabs
        items={VIEWS}
        value={view}
        onChange={(id) => {
          setView(id as View);
        }}
        label="AI and requests views"
      >
        {view === 'overview' && (
          <Stack gap={4}>
            <UsageBudgetPanel />
            <UsageTrendPanel />
            <Grid columns={2} gap={4} collapse="lg" align="start">
              <UsageBreakdownPanel />
              <UsageReliabilityPanel />
            </Grid>
          </Stack>
        )}
        {view === 'calls' && (
          <Suspense
            fallback={<Skeleton variant="table" rows={6} columns={4} label="Loading calls…" />}
          >
            <CallsSection
              selected={selected}
              onSelectCall={onSelectCall}
              onClearCall={onClearCall}
            />
          </Suspense>
        )}
        {view === 'requests' && (
          <Suspense
            fallback={<Skeleton variant="table" rows={6} columns={4} label="Loading requests…" />}
          >
            <RequestsSection />
          </Suspense>
        )}
      </Tabs>
    </Stack>
  );
}
