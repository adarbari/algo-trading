import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Surface } from '../../primitives/Surface';
import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Chip } from '../Chip';
import { StatusBadge } from '../StatusBadge';
import { Panel } from './Panel';

const meta = {
  title: 'Components/Panel',
  component: Panel,
  args: {
    title: 'Universe',
    children: (
      <Stack gap={2}>
        <Text mono size="sm">
          selection: vrp_universe
        </Text>
        <Text tone="secondary">
          Active optionable common stock, ADRs and ETFs. Leveraged ETFs included and flagged.
        </Text>
      </Stack>
    ),
  },
} satisfies Meta<typeof Panel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Header with description and actions, a body and a footer note. */
export const WithActions: Story = {
  args: {
    title: 'Preview',
    description: '14 qualified · 22 watch · 9 event risk',
    actions: (
      <>
        <Chip label="Near 52w high" defaultSelected onSelectedChange={() => undefined} />
        <Chip label="Watchlist" onSelectedChange={() => undefined} />
        <Button size="sm">Compare selected</Button>
      </>
    ),
    footer: 'Sample preview data. Score is for sorting only.',
    children: (
      <Stack gap={1}>
        <Stack direction="row" gap={2} align="center">
          <Text mono weight="medium">
            AAPL
          </Text>
          <StatusBadge tone="positive">QUALIFIED</StatusBadge>
        </Stack>
        <Stack direction="row" gap={2} align="center">
          <Text mono weight="medium">
            MSFT
          </Text>
          <StatusBadge tone="accent">WATCH</StatusBadge>
        </Stack>
      </Stack>
    ),
  },
};

export const Loading: Story = { args: { state: 'loading', loadingLabel: 'Loading ideas…' } };

export const Empty: Story = {
  args: {
    title: 'Top ideas',
    state: 'empty',
    emptyMessage: 'No screener qualified a name for Mon 5 Oct. Loosen a criterion or add one.',
  },
};

export const Error: Story = {
  args: {
    title: 'Completeness',
    state: 'error',
    errorMessage: 'The run index could not be read.',
    onRetry: () => undefined,
  },
};

/** Flush body for an edge-to-edge list, compact rows. */
export const Dense: Story = {
  args: {
    title: 'Your screeners',
    description: 'drag to reorder',
    flush: true,
    children: (
      <Stack gap={0}>
        {['VRP scanner', 'Cash-secured puts', 'Momentum breakouts', 'Earnings crush'].map(
          (name, i) => (
            <Surface
              key={name}
              border="bottom"
              borderTone="soft"
              radius="none"
              paddingX={4}
              paddingY={1.5}
            >
              <Stack direction="row" gap={3} align="center">
                <Text tone="muted">{i + 1}</Text>
                <Stack grow>
                  <Text>{name}</Text>
                </Stack>
                <Text weight="semibold">{[14, 9, 31, 4][i]}</Text>
              </Stack>
            </Surface>
          ),
        )}
      </Stack>
    ),
  },
};
