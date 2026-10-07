/**
 * Trader > Calendar: what is coming across names for the next 90 days (earnings, macro
 * releases, expiry days), for the site's scope list or the names a screener picked.
 */
import { Heading, Stack, Text } from '@algotrade/ui';

import { EventCalendarPanel } from '@/widgets/event-calendar-panel';

export function CalendarPage() {
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Calendar</Heading>
        <Text size="sm" tone="secondary">
          What is coming for many names at once, so an option is not sold into a report or a
          release. Choose the scope list or the picks of one of your screeners.
        </Text>
      </Stack>
      <EventCalendarPanel />
    </Stack>
  );
}
