/**
 * The monthly map: what the curve gained or lost in each calendar month, one row per year (a year
 * the split falls in is two rows, one per side), a column per month, each cell the month's value
 * as the server sent it and a loss tinted. Its own read (`edgeResult.monthly`). States: loading,
 * error, unknown, ready.
 */
import { DataTable, ErrorState, Skeleton, type DataTableColumn } from '@algotrade/ui';
import { useMemo } from 'react';

import { UnknownNote } from '@/entities/availability';
import { EDGE_UNKNOWN_WORDS, periodLabel, useEdgeMonthly, type EdgeMonthly } from '@/entities/edge';

const MONTHS = Array.from({ length: 12 }, (_, i) => ({
  id: String(i + 1).padStart(2, '0'),
  label: new Date(Date.UTC(2000, i, 1)).toLocaleString('en', { month: 'short', timeZone: 'UTC' }),
}));

/** One year (or one side of the split in the year it falls in) with its months' values by month number. */
interface YearRow {
  id: string;
  label: string;
  values: Record<string, number | undefined>;
}

function rowsOf(months: EdgeMonthly['months']): YearRow[] {
  const rows = new Map<string, YearRow>();
  for (const m of months) {
    const [year = '', month = ''] = m.month.split('-');
    const id = `${year}:${m.period}`;
    const row = rows.get(id) ?? {
      id,
      label: m.period === 'out_of_sample' ? `${year} · ${periodLabel(m.period)}` : year,
      values: {},
    };
    row.values[month] = m.value;
    rows.set(id, row);
  }
  return [...rows.values()];
}

const columns: DataTableColumn<YearRow>[] = [
  { id: 'year', header: 'Year', value: (r) => r.label, align: 'start', hideable: false },
  ...MONTHS.map((month): DataTableColumn<YearRow> => ({
    id: month.id,
    header: month.label,
    value: (r) => r.values[month.id],
    format: { kind: 'delta', unit: 'percent', digits: 1 },
    width: 'xs',
    sortable: false,
    fill: (r) => ((r.values[month.id] ?? 0) < 0 ? 'negative' : undefined),
  })),
];

export interface EdgeMonthlyProps {
  edgeId: string;
}

export function EdgeMonthly({ edgeId }: EdgeMonthlyProps) {
  const query = useEdgeMonthly(edgeId);
  const monthly = query.data;
  const rows = useMemo(() => rowsOf(monthly?.months ?? []), [monthly]);
  if (query.isPending) return <Skeleton variant="rect" label="Loading the monthly map" />;
  if (query.isError || !monthly) {
    return (
      <ErrorState
        compact
        title="The monthly map failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (monthly.unknown)
    return <UnknownNote unknown={monthly.unknown} kindWords={EDGE_UNKNOWN_WORDS} />;
  return (
    <DataTable<YearRow>
      label="Gain or loss of the curve by month"
      columns={columns}
      rows={rows}
      getRowId={(r) => r.id}
      emptyMessage="No months to show"
      visibleRows={8}
    />
  );
}
