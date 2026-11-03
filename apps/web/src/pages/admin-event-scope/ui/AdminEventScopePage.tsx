/**
 * Admin > Event scope: the names the event study covers by the site list and the admin's
 * changes, with each name's last deep-dive review and the share of its big moves attributed
 * (ADR 0050). The page only lays the widget out.
 */
import { Heading, Stack } from '@algotrade/ui';

import { EventScopeList } from '@/widgets/event-scope-list';

export function AdminEventScopePage() {
  return (
    <Stack gap={4}>
      <Heading level={1}>Event scope</Heading>
      <EventScopeList />
    </Stack>
  );
}
