import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../Stack';
import { Mono } from './Mono';

const meta = {
  title: 'Primitives/Mono',
  component: Mono,
  args: { children: 'SPY 261016P00575000' },
  parameters: {
    states: {
      notApplicable: {
        Loading:
          'Mono renders content it is given; loading placeholders are the Skeleton component',
        Empty: 'an empty Mono renders nothing; empty data is the EmptyState component',
        Error: 'Mono has no error state; errors are ErrorState / Banner',
      },
    },
  },
} satisfies Meta<typeof Mono>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Variants: Story = {
  render: () => (
    <Stack gap={1}>
      <Mono weight="medium">algotrade</Mono>
      <Mono tone="secondary">EQ:BBG000BDTBL9</Mono>
      <Mono tone="muted" size="sm">
        run 2026-10-02T06:12Z · 7f3a9c1
      </Mono>
      <Mono code>vrp_scanner.min_iv_rank</Mono>
    </Stack>
  ),
};

export const Dense: Story = {
  render: () => (
    <Stack gap={0}>
      {['AAPL', 'MSFT', 'NVDA', 'SPY'].map((s) => (
        <Mono key={s} size="md">
          {s}
        </Mono>
      ))}
    </Stack>
  ),
};

export const Truncated: Story = {
  args: { truncate: true, children: 'EQ:BBG000BDTBL9/chains/2026-10-02/'.repeat(5) },
};
