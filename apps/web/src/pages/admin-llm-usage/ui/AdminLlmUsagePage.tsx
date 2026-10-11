/**
 * Admin › LLM usage & cost: what the text model spends, so the cost never blows up. Spend by
 * window against the budget caps; the last 30 days by day; where it goes (model, use case, user,
 * cost basis, outcome); fallbacks and failures; and the latest calls beside the chosen call's
 * detail. The chosen call comes from the route (shareable); the page only lays the widgets out.
 */
import { Grid, Heading, Skeleton, Stack } from '@algotrade/ui';
import { lazy, Suspense } from 'react';

import { UsageBreakdownPanel } from '@/widgets/usage-breakdown-panel';
import { UsageBudgetPanel } from '@/widgets/usage-budget-panel';
import { UsageReliabilityPanel } from '@/widgets/usage-reliability-panel';
import { UsageTrendPanel } from '@/widgets/usage-trend-panel';

// One lazy chunk for the calls list and its detail (each lazy import adds a dependency list to
// the page chunk, so there is one, not one per widget).
const CallsSection = lazy(() => import('./CallsSection'));

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
  return (
    <Stack gap={4}>
      <Heading level={1}>LLM usage &amp; cost</Heading>
      <UsageBudgetPanel />
      <UsageTrendPanel />
      <Grid columns={2} gap={4} collapse="lg" align="start">
        <UsageBreakdownPanel />
        <UsageReliabilityPanel />
      </Grid>
      <Suspense fallback={<Skeleton variant="table" rows={6} columns={4} label="Loading calls…" />}>
        <CallsSection selected={selected} onSelectCall={onSelectCall} onClearCall={onClearCall} />
      </Suspense>
    </Stack>
  );
}
