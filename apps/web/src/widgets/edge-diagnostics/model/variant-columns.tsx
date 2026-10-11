/**
 * The columns of the variant grid (every screen at every holding period the run tried): the lift
 * of each period with its trades, the verdict's basis marked, every other row's out-of-sample
 * figure labelled as not the pre-chosen test. Every figure and flag is the server's.
 */
import { Stack, StatusBadge, Text, type DataTableColumn } from '@algotrade/ui';

import type { EdgeVariant, VariantFigures } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

const LIFT = { kind: 'delta', unit: 'points', digits: 1 } as const;

const figures = (row: EdgeVariant, period: 'inSample' | 'outOfSample' | 'all') => row[period];

const periodColumn = (
  id: string,
  header: string,
  period: 'inSample' | 'outOfSample' | 'all',
  emphasis = false,
): DataTableColumn<EdgeVariant> => ({
  id,
  header,
  value: (r) => figures(r, period)?.liftPts,
  format: LIFT,
  emphasis,
  essential: emphasis,
  cell: ({ row, formatted }) => {
    const f: VariantFigures | null = figures(row, period);
    if (!f || f.liftPts == null) return <Text tone="muted">Not stored</Text>;
    return (
      <Stack gap={0} align="end">
        <Stack direction="row" gap={1} align="center" justify="end">
          <Text tone={formatted.tone}>{formatted.text}</Text>
          <Text tone="muted">{`(${String(f.trades ?? 0)})`}</Text>
        </Stack>
        {emphasis && row.notPreChosen && (
          <Text tone="muted" size="sm">
            not the pre-chosen test
          </Text>
        )}
        {period === 'inSample' && row.modelFit && (
          <Text tone="muted" size="sm">
            training fit
          </Text>
        )}
      </Stack>
    );
  },
});

export const variantColumns: DataTableColumn<EdgeVariant>[] = [
  {
    id: 'variant',
    header: 'Variant',
    value: (r) => r.variant,
    align: 'start',
    hideable: false,
    cell: ({ row }) => (
      <Stack direction="row" gap={1} align="center" wrap>
        <Text>{row.variant}</Text>
        {row.official && (
          <>
            <StatusBadge tone="info">Verdict basis</StatusBadge>
            {termHelp('verdict_basis')}
          </>
        )}
      </Stack>
    ),
  },
  {
    id: 'horizon',
    header: 'Holding period',
    value: (r) => r.horizonSessions,
    format: { kind: 'number' },
    cell: ({ row }) => <Text>{`${String(row.horizonSessions)} trading days`}</Text>,
  },
  periodColumn('in_sample', 'In-sample', 'inSample'),
  periodColumn('out_of_sample', 'Out-of-sample', 'outOfSample', true),
  periodColumn('all', 'All', 'all'),
];
