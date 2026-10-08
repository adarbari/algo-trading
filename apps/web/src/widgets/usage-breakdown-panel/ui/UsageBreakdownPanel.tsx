/**
 * The last 30 days by model, use case, user, cost basis or outcome: calls, tokens, what counts
 * against the budget, the notional part of it and the share of the spend, most spent first. The
 * cost-basis view also draws the split as a bar, the notional seat cost in its own colour.
 */
import { DataTable, SegmentedControl, Stack, StackedBar } from '@algotrade/ui';
import { useState } from 'react';

import {
  BASIS_LABEL,
  BREAKDOWN_LABEL,
  UsagePanel,
  USD,
  type UsageBreakdown,
} from '@/entities/llm-usage';
import { GuideHelp } from '@/features/guide-help';

import { sliceColumns } from '../model/columns';

const OPTIONS = Object.entries(BREAKDOWN_LABEL).map(([value, label]) => ({ value, label }));
const BASIS_TONE = { price: 'accent', reported: 'info', bound: 'warning' } as const;

function BasisBar({ breakdown }: { breakdown: UsageBreakdown }) {
  const segments = breakdown.rows.flatMap((r) => {
    const tone = r.key ? BASIS_TONE[r.key as keyof typeof BASIS_TONE] : undefined;
    return tone && r.tally.spentUsd > 0
      ? [{ id: r.key ?? '', label: BASIS_LABEL[r.key ?? ''] ?? '', value: r.tally.spentUsd, tone }]
      : [];
  });
  return <StackedBar label="Spend by cost basis" segments={segments} format={USD} size="md" />;
}

export function UsageBreakdownPanel() {
  const [by, setBy] = useState('model');
  return (
    <UsagePanel
      title="Where the spend goes"
      description="last 30 days"
      actions={<GuideHelp entry={{ kind: 'term', id: 'llm_cost_basis' }} />}
    >
      {(usage) => {
        const breakdown = usage.breakdowns.find((b) => b.by === by);
        return (
          <Stack gap={3}>
            <SegmentedControl
              aria-label="Break down by"
              options={OPTIONS}
              value={by}
              onValueChange={setBy}
            />
            {breakdown && by === 'cost_basis' && <BasisBar breakdown={breakdown} />}
            <DataTable
              label={`Usage by ${BREAKDOWN_LABEL[by] ?? by}`}
              columns={sliceColumns(by)}
              rows={breakdown?.rows ?? []}
              getRowId={(s) => `${s.provider ?? ''}~${s.key ?? ''}`}
              visibleRows={8}
            />
          </Stack>
        );
      }}
    </UsagePanel>
  );
}
