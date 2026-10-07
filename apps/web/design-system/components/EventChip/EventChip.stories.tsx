import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { EventChip } from './EventChip';
import { EVENT_KIND_NAMES, EVENT_KINDS } from './eventKinds';
import { cpi, earnings, fomc, oneOfEach, opex, results } from '../../testing';

const meta = {
  title: 'Components/EventChip',
  component: EventChip,
  args: { kind: 'own_earnings', label: 'Earnings' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a chip labels an event that already exists; the container shows loading',
        Empty: 'a chip labels an event that already exists; the container shows the empty state',
        Error: 'a chip labels an event that already exists; the container shows the error',
      },
    },
  },
} satisfies Meta<typeof EventChip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** The five kinds side by side: the colour and the glyph both say which. */
export const AllKinds: Story = {
  render: () => (
    <Stack direction="row" gap={1.5} wrap>
      <EventChip kind="own_earnings" label="Earnings" />
      <EventChip kind="reference_earnings" label="NVDA earnings" />
      <EventChip kind="macro_release" label="CPI" />
      <EventChip kind="market_structure" label="Opex" />
      <EventChip kind="filing" label="2.02 results" />
    </Stack>
  ),
};

/** With the event: focus or hover shows its time, source and the day it became known. */
export const WithDetails: Story = {
  render: () => (
    <Stack direction="row" gap={1.5} wrap>
      {oneOfEach.map((event) => (
        <EventChip key={event.label} kind={event.kind} label={event.label} event={event} />
      ))}
    </Stack>
  ),
};

/** A narrow cell: a long label truncates inside the chip. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1.5}>
      <Stack direction="row" gap={1} wrap>
        {[earnings, cpi, fomc, opex, results, earnings, cpi, fomc].map((event, i) => (
          <EventChip key={i} kind={event.kind} label={event.label} />
        ))}
      </Stack>
      <Stack gap={1} align="start">
        {EVENT_KINDS.map((kind) => (
          <Text key={kind} size="xs" tone="muted">
            {EVENT_KIND_NAMES[kind]}
          </Text>
        ))}
      </Stack>
    </Stack>
  ),
};
