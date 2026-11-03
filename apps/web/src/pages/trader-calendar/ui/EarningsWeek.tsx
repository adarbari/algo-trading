/**
 * Earnings week: the names reporting in the next five sessions, one row each, with what the
 * options price for the report beside how far the name has moved on its past ones. The rows are
 * the calendar's `own_earnings` events; every figure is a catalogue column read by name through
 * the feature table (ADR 0038), so a fact not stored yet is UNKNOWN with its reason, never a
 * blank. The shared filter bar (ADR 0082, surface `calendar_week`: report day and time, the priced
 * move and how it compares with the usual one, sector, share and option liquidity, saved views)
 * narrows the list on the server; the filters in force are the page's `f` search param. Says
 * nothing about direction.
 */
import { formatValue, Banner, EmptyState, Stack, Text, type DataTableSort } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { earningsWeek, gapLines, useEventCalendar } from '@/entities/event';
import { feature } from '@/shared/api';
import { CalendarSourcePicker, useCalendarSource } from '@/features/calendar-source';
import { SurfaceFilterBar, SurfaceZeroResults, useFilterState } from '@/features/filter-bar';
import { termHelp } from '@/features/guide-help';
import { FeatureTable } from '@/widgets/feature-table';

/** The surface of the filter bar: its definitions are `config/site/filters/calendar_week.toml`. */
const SURFACE = 'calendar_week';

/**
 * Report date and time, the expiry used, the priced move, the mean of the past 12 moves, priced
 * against usual, and how often options priced more than the move (UNKNOWN until stored).
 */
const EARNINGS_WEEK_COLUMNS = [
  feature('rollup.earnings@v1.next_earnings_date'),
  feature('rollup.earnings@v1.earnings_time'),
  feature('rollup.implied_move@v1.move_expiry'),
  feature('rollup.implied_move@v1.implied_move'),
  feature('rollup.earnings_moves@v1.abs_move_mean_12'),
  feature('feature.earnings_move_vs_usual'),
  feature('rollup.earnings_moves@v1.options_overpaid_n'),
  feature('rollup.earnings_moves@v1.options_overpaid_m'),
];

const dayText = (iso: string) => formatValue(iso, { kind: 'date', style: 'weekday' }).text;

export interface EarningsWeekProps {
  /** The filter bar's `f` search param (the filters in force) and its writer (the route's). */
  f: string | undefined;
  onFilterChange: (f: string | undefined) => void;
}

export function EarningsWeek({ f, onFilterChange }: EarningsWeekProps) {
  const source = useCalendarSource();
  const calendar = useEventCalendar(source.ids, source.scope, source.ready);
  const week = useMemo(() => (calendar.data ? earningsWeek(calendar.data) : null), [calendar.data]);
  const gaps = useMemo(() => gapLines(calendar.data?.gaps ?? []), [calendar.data]);
  const [columns, setColumns] = useState<string[]>(EARNINGS_WEEK_COLUMNS);
  const [sort, setSort] = useState<DataTableSort | null>(null);
  const filters = useFilterState(f, onFilterChange);
  const settled = !calendar.isPending && !source.loading;
  const picker = (
    <CalendarSourcePicker
      value={source.value}
      screeners={source.screeners}
      onChange={source.setValue}
    />
  );
  const message = source.message !== null && <Banner tone="info">{source.message}</Banner>;
  if (settled && (week?.symbols.length ?? 0) === 0) {
    return (
      <Stack gap={2}>
        {picker}
        {message}
        <EmptyState
          bordered
          icon="search"
          title="No report in the next five sessions"
          description="None of these names has a report date in the next five sessions."
        />
      </Stack>
    );
  }
  return (
    <FeatureTable
      label={week ? `Earnings · ${dayText(week.from)} to ${dayText(week.to)}` : 'Earnings week'}
      keys={week?.symbols ?? []}
      columns={columns}
      onColumnsChange={setColumns}
      surface={SURFACE}
      filters={filters.filters}
      sortMode="server"
      sort={sort}
      onSortChange={setSort}
      header={(facets) => (
        <Stack gap={2}>
          {picker}
          {message}
          {gaps.length > 0 && (
            <Banner tone="info">
              <Stack gap={0.5}>
                {gaps.map((line) => (
                  <Text key={line} size="sm">
                    {line}
                  </Text>
                ))}
              </Stack>
            </Banner>
          )}
          <SurfaceFilterBar
            surface={SURFACE}
            views
            state={filters}
            facets={facets}
            help={(entry) => (entry.kind === 'term' ? termHelp(entry.id) : null)}
          />
        </Stack>
      )}
      emptyMessage={(facets) =>
        filters.filters.some((applied) => applied.active) ? (
          <SurfaceZeroResults surface={SURFACE} state={filters} facets={facets} />
        ) : (
          'No report in the next five sessions for these names.'
        )
      }
    />
  );
}
