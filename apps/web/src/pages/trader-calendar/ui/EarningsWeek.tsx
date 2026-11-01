/**
 * Earnings week: the names reporting in the next five sessions, one row each, with what the
 * options price for the report beside how far the name has moved on its past ones. The rows are
 * the calendar's `own_earnings` events; every figure is a catalogue column read by name through
 * the feature table (ADR 0038), so a fact not stored yet is UNKNOWN with its reason, never a
 * blank. Says nothing about direction.
 */
import { formatValue, Banner, Stack, Text } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { earningsWeek, gapLines, useEventCalendar } from '@/entities/event';
import { feature } from '@/shared/api';
import { CalendarSourcePicker, useCalendarSource } from '@/features/calendar-source';
import { FeatureTable } from '@/widgets/feature-table';

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

export function EarningsWeek() {
  const source = useCalendarSource();
  const calendar = useEventCalendar(source.ids, source.scope, source.ready);
  const week = useMemo(() => (calendar.data ? earningsWeek(calendar.data) : null), [calendar.data]);
  const gaps = useMemo(() => gapLines(calendar.data?.gaps ?? []), [calendar.data]);
  const [columns, setColumns] = useState<string[]>(EARNINGS_WEEK_COLUMNS);
  return (
    <FeatureTable
      label={week ? `Earnings · ${dayText(week.from)} to ${dayText(week.to)}` : 'Earnings week'}
      keys={week?.symbols ?? []}
      columns={columns}
      onColumnsChange={setColumns}
      sortMode="client"
      header={
        <Stack gap={2}>
          <CalendarSourcePicker
            value={source.value}
            screeners={source.screeners}
            onChange={source.setValue}
          />
          {source.message !== null && <Banner tone="info">{source.message}</Banner>}
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
        </Stack>
      }
      emptyMessage="No report in the next five sessions for these names."
    />
  );
}
