/**
 * Year by year: the verdict's basis (its screen and holding period) one calendar year per row,
 * with an In-sample / Out-of-sample / Both switch. The server marks each year's period (a year
 * the split falls in is `both` and shows under Both only); this only filters by that mark.
 */
import { DataTable, Panel, SegmentedControl, type SegmentedOption } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import type { VerdictYear } from '@/entities/edge';

import { yearColumns } from '../model/columns';

type View = 'in_sample' | 'out_of_sample' | 'both';

const OPTIONS: SegmentedOption<View>[] = [
  { value: 'in_sample', label: 'In-sample' },
  { value: 'out_of_sample', label: 'Out-of-sample' },
  { value: 'both', label: 'Both' },
];

const shows = (view: View, year: VerdictYear): boolean => view === 'both' || year.period === view;

export interface EdgeYearsProps {
  years: readonly VerdictYear[];
}

export function EdgeYears({ years }: EdgeYearsProps) {
  const [view, setView] = useState<View>('both');
  const rows = useMemo(() => years.filter((y) => shows(view, y)), [years, view]);
  return (
    <Panel
      title="Year by year"
      flush
      actions={
        <SegmentedControl
          aria-label="Period shown"
          size="sm"
          options={OPTIONS}
          value={view}
          onValueChange={setView}
        />
      }
    >
      <DataTable<VerdictYear>
        label="Year by year"
        columns={yearColumns}
        rows={rows}
        getRowId={(y) => y.year}
        emptyMessage="No years to show"
        visibleRows={8}
      />
    </Panel>
  );
}
