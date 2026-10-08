/**
 * The last 30 days by day: the cost that counts against the budget (with the notional seat cost
 * as its own line) and the tokens in and out. A day with no recorded calls is a zero of calls,
 * so it draws as a zero; the table view lists every day.
 */
import { Chart, Grid } from '@algotrade/ui';

import { TOKENS, UsagePanel, USD, type LlmUsage } from '@/entities/llm-usage';

function series(usage: LlmUsage) {
  const line = (id: string, label: string, value: (d: LlmUsage['daily'][number]) => number) => ({
    id,
    label,
    points: usage.daily.map((d) => ({ time: d.day, value: value(d) })),
  });
  return {
    cost: [
      line('spent', 'Counts against the budget', (d) => d.tally.spentUsd),
      line('reported', 'Notional (reported)', (d) => d.tally.reportedUsd),
    ],
    tokens: [
      line('in', 'Input tokens', (d) => d.tally.inputTokens),
      line('out', 'Output tokens', (d) => d.tally.outputTokens),
    ],
  };
}

export function UsageTrendPanel() {
  return (
    <UsagePanel title="Last 30 days" description="by exchange calendar day" rows={3}>
      {(usage) => {
        const lines = series(usage);
        return (
          <Grid columns={2} gap={4} collapse="lg">
            <Chart label="Cost per day" series={lines.cost} format={USD} height="sm" range="All" />
            <Chart
              label="Tokens per day"
              series={lines.tokens}
              format={TOKENS}
              height="sm"
              range="All"
            />
          </Grid>
        );
      }}
    </UsagePanel>
  );
}
