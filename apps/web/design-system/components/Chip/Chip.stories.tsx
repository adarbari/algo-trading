import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Chip } from './Chip';
import { narrow } from '../../testing';

const meta = {
  title: 'Components/Chip',
  component: Chip,
  args: { label: 'Optionable' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a chip is a local label or toggle; nothing loads',
      },
    },
  },
} satisfies Meta<typeof Chip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Filter chips: toggles, one selected, plus the dashed add chip (Explore filter bar). */
export const FilterBar: Story = {
  render: () => (
    <Stack direction="row" gap={1.5} wrap>
      <Chip label="Optionable" defaultSelected onSelectedChange={() => undefined} />
      <Chip label="Stock · ETF · ADR" onSelectedChange={() => undefined} />
      <Chip label="Liquidity: High" onSelectedChange={() => undefined} />
      <Chip label="Filter" icon="plus" variant="dashed" onClick={() => undefined} />
    </Stack>
  ),
};

export const Removable: Story = {
  render: () => (
    <Stack direction="row" gap={1.5} wrap>
      <Chip label="Sector: Technology" onRemove={() => undefined} />
      <Chip label="Near 52w high" selected onRemove={() => undefined} />
    </Stack>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Stack direction="row" gap={1.5}>
      <Chip label="Watchlist" disabled onSelectedChange={() => undefined} />
      <Chip label="Sector: Energy" disabled onRemove={() => undefined} />
    </Stack>
  ),
};

/** No filters applied: just the add chip, with a hint. */
export const Empty: Story = {
  render: () => (
    <Stack direction="row" gap={2} align="center">
      <Chip label="Filter" icon="plus" variant="dashed" onClick={() => undefined} />
      <Text size="sm" tone="muted">
        No filters: showing the whole universe
      </Text>
    </Stack>
  ),
};

export const Error: Story = {
  render: () => (
    <Stack gap={1}>
      <Chip label="Earnings < 14d" onRemove={() => undefined} />
      <Text size="sm" tone="negative">
        This filter needs earnings dates, which failed to load for Fri 2 Oct.
      </Text>
    </Stack>
  ),
};

/** Many chips wrapping in a narrow panel header. */
export const Dense: Story = {
  render: () => (
    <Stack direction="row" gap={1} wrap>
      {['Qualified', 'Watch', 'Event risk', 'ADR', 'Leveraged', 'Earnings < 14d', 'Watchlist'].map(
        (label, i) => (
          <Chip
            key={label}
            label={label}
            defaultSelected={i === 0}
            onSelectedChange={() => undefined}
          />
        ),
      )}
    </Stack>
  ),
};

/** A 375 px phone frame; under a coarse pointer the control floors apply. */
export const Narrow: Story = { ...Dense, decorators: [narrow] };
