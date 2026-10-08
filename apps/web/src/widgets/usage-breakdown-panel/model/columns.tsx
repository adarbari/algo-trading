/** The columns of a usage breakdown: one group (a model, a use case, a user, a cost basis, an outcome) per row. */
import type { DataTableColumn } from '@algotrade/ui';

import { PERCENT, sliceLabel, TOKENS, USD, type UsageSlice } from '@/entities/llm-usage';

export function sliceColumns(by: string): DataTableColumn<UsageSlice>[] {
  return [
    {
      id: 'key',
      header: 'Group',
      value: (s) => sliceLabel(by, s.key),
      cell: ({ row }) =>
        row.provider ? `${row.key ?? '—'} · ${row.provider}` : sliceLabel(by, row.key),
      grow: true,
    },
    { id: 'calls', header: 'Calls', value: (s) => s.tally.calls, format: TOKENS, align: 'end' },
    {
      id: 'input',
      header: 'Input tokens',
      description: 'summed over the calls that reported them',
      value: (s) => s.tally.inputTokens,
      format: TOKENS,
      align: 'end',
    },
    {
      id: 'output',
      header: 'Output tokens',
      value: (s) => s.tally.outputTokens,
      format: TOKENS,
      align: 'end',
    },
    {
      id: 'spent',
      header: 'Counts against budget',
      value: (s) => s.tally.spentUsd,
      format: USD,
      align: 'end',
    },
    {
      id: 'reported',
      header: 'of which notional',
      description: 'the Claude Code login’s reported cost: not billed',
      value: (s) => s.tally.reportedUsd,
      format: USD,
      align: 'end',
    },
    {
      id: 'share',
      header: 'Share of spend',
      value: (s) => s.costShare,
      format: PERCENT,
      align: 'end',
    },
  ];
}
