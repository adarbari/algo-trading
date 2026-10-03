import type { Meta, StoryObj } from '@storybook/react-vite';

import { Mono } from '../Mono';
import { Text } from '../Text';
import { Stack } from './Stack';

const items = ['AAPL', 'MSFT', 'NVDA', 'SPY'];

const meta = {
  title: 'Primitives/Stack',
  component: Stack,
  args: {
    gap: 2,
    children: items.map((symbol) => <Mono key={symbol}>{symbol}</Mono>),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'Stack is layout only; loading is shown by the components it holds',
        Error: 'Stack is layout only; errors are shown by the components it holds',
      },
    },
  },
} satisfies Meta<typeof Stack>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Row: Story = { args: { direction: 'row', gap: 4, align: 'baseline' } };

export const Between: Story = {
  args: {
    direction: 'row',
    justify: 'between',
    children: [
      <Text key="l" tone="muted">
        Expiry
      </Text>,
      <Text key="r" numeric>
        2026-10-16
      </Text>,
    ],
  },
};

export const Cluster: Story = {
  args: {
    direction: 'row',
    wrap: true,
    gap: 3,
    children: [...items, 'QQQ', 'IWM', 'TLT', 'GLD', 'USO', 'XLE'].map((s) => (
      <Mono key={s}>{s}</Mono>
    )),
  },
};

export const Empty: Story = { args: { children: undefined } };

export const Dense: Story = { args: { gap: 0 } };

export const Landmark: Story = {
  args: { as: 'nav', 'aria-label': 'Primary', direction: 'row', gap: 3 },
};
