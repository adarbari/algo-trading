/**
 * Trader > Calendar, in three views under one heading: Earnings week (what options price for
 * each report next to the name's past moves), Next 90 days (the days-against-names grid of
 * earnings, macro releases and expiry days) and Macro (the market-wide days alone).
 */
import { Heading, Stack, Tabs, Text, type TabItem } from '@algotrade/ui';
import { useState } from 'react';

import { EarningsWeek } from './EarningsWeek';
import { EventsAhead } from './EventsAhead';
import { MacroDays } from './MacroDays';

const VIEWS: readonly TabItem[] = [
  { id: 'week', label: 'Earnings week' },
  { id: 'ahead', label: 'Next 90 days' },
  { id: 'macro', label: 'Macro' },
];

export function CalendarPage() {
  const [view, setView] = useState('week');
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Calendar</Heading>
        <Text size="sm" tone="secondary">
          What is coming for many names at once, so an option is not sold into a report or a
          release.
        </Text>
      </Stack>
      <Tabs label="Calendar views" items={VIEWS} value={view} onChange={setView}>
        {view === 'week' && <EarningsWeek />}
        {view === 'ahead' && <EventsAhead />}
        {view === 'macro' && <MacroDays />}
      </Tabs>
    </Stack>
  );
}
