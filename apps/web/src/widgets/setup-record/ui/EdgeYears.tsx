/**
 * Year by year: the verdict's basis (its screen and holding period) one calendar year per row,
 * with an In-sample / Out-of-sample / All switch. The server marks each row's period: a year the
 * split falls in is two rows (`2026 Jan–Mar` in-sample, `2026 Apr–Dec` out-of-sample); a run from
 * before that split is one `both` row, shown under All only. This only filters by that mark.
 */
import { DataTable, SegmentedControl, Stack, type SegmentedOption } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import type { VerdictYear } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { yearColumns } from '../model/columns';

type View = 'in_sample' | 'out_of_sample' | 'both';

const OPTIONS: SegmentedOption<View>[] = [
  { value: 'in_sample', label: 'In-sample' },
  { value: 'out_of_sample', label: 'Out-of-sample' },
  { value: 'both', label: 'All' },
];

const shows = (view: View, year: VerdictYear): boolean => view === 'both' || year.period === view;

export interface EdgeYearsProps {
  years: readonly VerdictYear[];
}

export function EdgeYears({ years }: EdgeYearsProps) {
  const [view, setView] = useState<View>('both');
  const rows = useMemo(() => years.filter((y) => shows(view, y)), [years, view]);
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <SegmentedControl
          aria-label="Period shown"
          size="sm"
          options={OPTIONS}
          value={view}
          onValueChange={setView}
        />
        {termHelp('year_by_year')}
      </Stack>
      <DataTable<VerdictYear>
        label="Year by year"
        columns={yearColumns}
        rows={rows}
        getRowId={(y) => `${y.year}:${y.period}`}
        emptyMessage="No years to show"
        visibleRows={8}
      />
    </Stack>
  );
}
