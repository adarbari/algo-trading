import type { Meta, StoryObj } from '@storybook/react-vite';

import { Text } from '../Text';
import { Stack } from './Stack';

const items = ['AAPL', 'MSFT', 'NVDA', 'SPY'];

const meta = {
  title: 'Primitives/Stack',
  component: Stack,
  args: {
    gap: 2,
    children: items.map((symbol) => (
      <Text key={symbol} mono>
        {symbol}
      </Text>
    )),
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
      <Text key="l" variant="label">
        Expiry
      </Text>,
      <Text key="r" numeric>
        2026-10-16
      </Text>,
    ],
  },
};

export const Empty: Story = { args: { children: undefined } };

export const Dense: Story = { args: { gap: 0 } };

export const Landmark: Story = {
  args: { as: 'nav', 'aria-label': 'Primary', direction: 'row', gap: 3 },
};
