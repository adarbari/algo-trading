/**
 * Macro: the market-wide days of the next 90 days (macro releases, option expiries, index and
 * quarter-end dates) on one timeline, with the parts the session does not know said above it.
 * What an event is and when it is known from are the API's.
 */
import { Banner, EventTimeline, Panel, Stack, Text } from '@algotrade/ui';
import { useMemo } from 'react';

import { gapLines, macroItems, useEventCalendar } from '@/entities/event';
import { SCOPE_SOURCE } from '@/features/calendar-source';
import { termHelp } from '@/features/guide-help';

export function MacroCalendar() {
  const calendar = useEventCalendar([], true, true);
  const items = useMemo(() => (calendar.data ? macroItems(calendar.data) : []), [calendar.data]);
  const gaps = useMemo(
    () => gapLines((calendar.data?.gaps ?? []).filter((g) => g.instrumentId === null)),
    [calendar.data],
  );
  return (
    <Panel
      title="Macro and market days"
      description="Releases, option expiries and index dates for the whole market"
      actions={termHelp('macro_days')}
      state={calendar.isError ? 'error' : 'ready'}
      errorMessage="The macro calendar failed to load."
      onRetry={() => void calendar.refetch()}
    >
      <Stack gap={3}>
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
        <EventTimeline
          label={`Market-wide events, next 90 days (${SCOPE_SOURCE})`}
          events={items}
          start={calendar.data?.session ?? ''}
          end={calendar.data?.end ?? ''}
          status={calendar.isPending ? 'loading' : 'ready'}
          emptyMessage="No market-wide event is stored for the next 90 days."
        />
      </Stack>
    </Panel>
  );
}
