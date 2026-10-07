/**
 * Calendar: the next 90 days of events across names, days against names, the expiry Fridays
 * ruled. The names are the site's scope list or the picks of a chosen screener's latest run;
 * what a cell, a Market column entry or a gap says is the API's.
 */
import { CalendarGrid, Banner, Panel, Stack, Text } from '@algotrade/ui';
import { useMemo } from 'react';

import { calendarDays, gapLines, useEventCalendar } from '@/entities/event';
import { CalendarSourcePicker, useCalendarSource } from '@/features/calendar-source';

export function EventCalendarPanel() {
  const source = useCalendarSource();
  const calendar = useEventCalendar(source.ids, source.scope, source.ready);
  const grid = useMemo(() => (calendar.data ? calendarDays(calendar.data) : null), [calendar.data]);
  const gaps = useMemo(() => gapLines(calendar.data?.gaps ?? []), [calendar.data]);
  const missing = calendar.data ? [...calendar.data.missing, ...calendar.data.unresolved] : [];
  const what = source.scope ? 'scope list' : source.value;
  const failed = calendar.isError || source.failed;
  const waiting = source.loading || (source.ready && calendar.isPending);
  return (
    <Panel
      title="Events ahead"
      description="The next 90 days of earnings, macro releases and expiry days"
      actions={
        <CalendarSourcePicker
          value={source.value}
          screeners={source.screeners}
          onChange={source.setValue}
        />
      }
      state={failed ? 'error' : 'ready'}
      errorMessage="The calendar failed to load."
      onRetry={() => void calendar.refetch()}
    >
      <Stack gap={3}>
        {source.message !== null && <Banner tone="info">{source.message}</Banner>}
        {gaps.length > 0 && (
          <Banner tone="info" title="Not known for this session">
            <Stack gap={0.5}>
              {gaps.map((line) => (
                <Text key={line} size="sm">
                  {line}
                </Text>
              ))}
            </Stack>
          </Banner>
        )}
        {missing.length > 0 && (
          <Banner tone="info" title="Not in the session's snapshot">
            <Text size="sm">{missing.join(', ')}</Text>
          </Banner>
        )}
        <CalendarGrid
          label={`Events, next 90 days: ${what}`}
          days={grid?.days ?? []}
          names={grid?.names ?? []}
          ruledDays={grid?.ruledDays ?? []}
          ruleLabel="Expiry"
          status={waiting ? 'loading' : 'ready'}
          emptyMessage={
            calendar.data === null
              ? 'No events are stored for the session.'
              : 'No events in the next 90 days for these names.'
          }
        />
      </Stack>
    </Panel>
  );
}
