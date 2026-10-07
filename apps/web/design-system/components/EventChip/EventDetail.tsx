/**
 * EventDetail: the hover and focus text of one event: its label, kind, day and time, source and
 * the day it became known. One place for the wording, used by the chips' tooltip and by the
 * dense collapsed views of the other event components.
 */
import { formatValue } from '../../format';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { EVENT_KIND_NAMES, timeText, type EventItem } from './eventKinds';

const day = (value: string) => formatValue(value, { kind: 'date', style: 'weekday' }).text;
const shortDay = (value: string) => formatValue(value, { kind: 'date', style: 'short' }).text;

export function EventDetail({ event }: { event: EventItem }) {
  return (
    <Stack gap={0.5}>
      <Text size="sm" weight="semibold">
        {event.label}
      </Text>
      <Text size="xs" tone="muted">
        {`${EVENT_KIND_NAMES[event.kind]}: ${day(event.date)}, ${timeText(event.time)}`}
      </Text>
      <Text size="xs" tone="muted">
        {`Source: ${event.source}`}
      </Text>
      <Text size="xs" tone="muted">
        {`Known from ${shortDay(event.knownFrom)}`}
      </Text>
    </Stack>
  );
}
