/**
 * Admin › LLM usage & cost: what the text model spends, so the cost never blows up. Spend by
 * window against the budget caps; the last 30 days by day; where it goes (model, use case, user,
 * cost basis, outcome); fallbacks and failures; and the latest calls beside the chosen call's
 * detail. The chosen call comes from the route (shareable); the page only lays the widgets out.
 */
import { Grid, Heading, MasterDetail, Stack } from '@algotrade/ui';

import { UsageBreakdownPanel } from '@/widgets/usage-breakdown-panel';
import { UsageBudgetPanel } from '@/widgets/usage-budget-panel';
import { UsageCallDetail } from '@/widgets/usage-call-detail';
import { UsageCallsPanel } from '@/widgets/usage-calls-panel';
import { UsageReliabilityPanel } from '@/widgets/usage-reliability-panel';
import { UsageTrendPanel } from '@/widgets/usage-trend-panel';

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
      <MasterDetail
        columns="main-aside"
        collapse="lg"
        master={<UsageCallsPanel selected={selected} onSelect={onSelectCall} />}
        detail={<UsageCallDetail selected={selected} />}
        detailKey={selected}
        detailTitle="Call detail"
        onDetailClose={onClearCall}
      />
    </Stack>
  );
}
