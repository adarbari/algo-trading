/** The columns of the recent calls: one stored attempt per row, every column of the log. */
import type { DataTableColumn } from '@algotrade/ui';

import { BasisBadge, OutcomeBadge, stamp, TOKENS, USD, type UsageCall } from '@/entities/llm-usage';

export const CALL_COLUMNS: DataTableColumn<UsageCall>[] = [
  { id: 'ts', header: 'When', value: (c) => c.ts, cell: ({ row }) => stamp(row.ts), mono: true },
  { id: 'provider', header: 'Provider', value: (c) => c.provider },
  { id: 'model', header: 'Model', value: (c) => c.model, mono: true },
  { id: 'useCase', header: 'Use case', value: (c) => c.useCase },
  { id: 'user', header: 'User', value: (c) => c.user },
  {
    id: 'input',
    header: 'Input tokens',
    value: (c) => c.inputTokens,
    format: TOKENS,
    align: 'end',
  },
  {
    id: 'output',
    header: 'Output tokens',
    value: (c) => c.outputTokens,
    format: TOKENS,
    align: 'end',
  },
  {
    id: 'latency',
    header: 'Latency (s)',
    value: (c) => c.latencyS,
    format: { kind: 'number', digits: 1 },
    align: 'end',
  },
  { id: 'cost', header: 'Cost', value: (c) => c.costUsd, format: USD, align: 'end' },
  {
    id: 'basis',
    header: 'Cost basis',
    value: (c) => c.costBasis,
    cell: ({ row }) => <BasisBadge basis={row.costBasis} />,
  },
  {
    id: 'outcome',
    header: 'Outcome',
    value: (c) => c.outcome,
    cell: ({ row }) => <OutcomeBadge outcome={row.outcome} />,
  },
];
