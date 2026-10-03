import type { Meta, StoryObj } from '@storybook/react-vite';

import { Mono } from '../../primitives/Mono';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Disclosure } from './Disclosure';

const meta = {
  title: 'Components/Disclosure',
  component: Disclosure,
  args: {
    label: 'Stale: Cboe’s latest chain is from an earlier day',
    count: '515',
    defaultOpen: true,
    children: (
      <>
        <Mono size="xs" tone="secondary">
          ACIU 2026-10-01 · ALLT 2026-10-01 · AOSL 2026-10-01 · … 512 more
        </Mono>
        <Text size="sm" tone="muted">
          Thin names with no Friday trades. Screens treat them as UNKNOWN.
        </Text>
      </>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a disclosure shows content it is given; its parent panel shows loading',
        Empty: 'a group with no members is not rendered (its count would be zero)',
        Error: 'a disclosure holds no data of its own; its parent panel shows a failed load',
      },
    },
  },
} satisfies Meta<typeof Disclosure>;

export default meta;
type Story = StoryObj<typeof meta>;

/** One group of issues, open. */
export const Default: Story = {};

export const Closed: Story = {
  args: { defaultOpen: false, label: 'No chain published', count: '63' },
};

/** Grouped issues as in the ingestion drill-down. */
export const Grouped: Story = {
  render: () => (
    <Stack gap={2}>
      <Disclosure
        label="Stale: Cboe’s latest chain is from an earlier day"
        count="515"
        countTone="warning"
        defaultOpen
      >
        <Mono size="xs" tone="secondary">
          ACIU 2026-10-01 · ALLT 2026-10-01 · … 513 more
        </Mono>
      </Disclosure>
      <Disclosure label="No chain published" count="63">
        <Mono size="xs" tone="secondary">
          XMAX · IMDX · ESGU · … 60 more
        </Mono>
      </Disclosure>
      <Disclosure label="Fetch errors" count="0" countTone="muted">
        <Text size="sm" tone="muted">
          None this session.
        </Text>
      </Disclosure>
    </Stack>
  ),
};

/** Plain rows: a list that draws its own dividers. */
export const Dense: Story = {
  render: () => (
    <Stack gap={0}>
      {['Hard criteria', 'Soft criteria', 'Universe rules'].map((label, i) => (
        <Disclosure key={label} label={label} count={String(3 + i)} variant="plain">
          <Text size="sm">Details for {label.toLowerCase()}.</Text>
        </Disclosure>
      ))}
    </Stack>
  ),
};
