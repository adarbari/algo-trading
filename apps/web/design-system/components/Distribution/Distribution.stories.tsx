import type { Meta, StoryObj } from '@storybook/react-vite';

import { Distribution, type DistributionBin } from './Distribution';

/** A right-skewed spread of IV30 across the optionable universe (sample counts). */
const iv30: DistributionBin[] = [42, 118, 236, 344, 361, 287, 192, 121, 70, 38, 21, 9, 5, 2].map(
  (count, i) => ({ start: 0.05 + i * 0.05, end: 0.1 + i * 0.05, count }),
);

const meta = {
  title: 'Components/Distribution',
  component: Distribution,
  args: {
    bins: iv30,
    label: 'IV30 across 1,846 tickers',
    format: { kind: 'percent', digits: 0 },
  },
} satisfies Meta<typeof Distribution>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Quantile markers (dashed) and the focused ticker (solid accent). */
export const Default: Story = {
  args: {
    markers: [
      { value: 0.16, label: 'p10' },
      { value: 0.27, label: 'median' },
      { value: 0.46, label: 'p90' },
      { value: 0.244, label: 'AAPL', tone: 'accent' },
    ],
  },
};

/** A long right tail: close quantiles would collide, so labels stack or drop; AAPL stays. */
export const Skewed: Story = {
  args: {
    markers: [
      { value: 0.24, label: 'median' },
      { value: 0.17, label: 'p10' },
      { value: 0.38, label: 'p90' },
      { value: 0.21, label: 'p25' },
      { value: 0.31, label: 'p75' },
      { value: 0.62, label: 'p99' },
      { value: 0.23, label: 'AAPL', tone: 'accent' },
    ],
  },
};

/** The names passing a criterion (the part of each bin that passes) in the accent over the rest. */
export const Highlighted: Story = {
  args: {
    bins: iv30.map((bin, i) => ({
      ...bin,
      highlighted: i < 3 ? bin.count : i === 3 ? Math.round(bin.count / 3) : 0,
    })),
    highlightLabel: 'at or below 25% IV30',
    markers: [{ value: 0.27, label: 'median' }],
  },
};

/** Bars only. */
export const Plain: Story = {};

export const Loading: Story = { args: { status: 'loading' } };

export const Empty: Story = { args: { bins: [], emptyMessage: 'No ticker has IV30 yet.' } };

export const Error: Story = {
  args: {
    status: 'error',
    errorMessage: 'The distribution could not load.',
    onRetry: () => undefined,
  },
};

/** The short plot for a catalogue row. */
export const Dense: Story = {
  args: { height: 'sm', markers: [{ value: 0.27, label: 'median' }] },
};
