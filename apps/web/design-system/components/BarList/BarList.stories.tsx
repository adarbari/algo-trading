import type { Meta, StoryObj } from '@storybook/react-vite';

import { BarList, type BarListItem } from './BarList';

const tiers: BarListItem[] = [
  { id: 'etf', label: 'Priority ETFs (33)', value: 1, display: '100%' },
  { id: 'spx', label: 'S&P 500 (503)', value: 0.996, display: '99.6%' },
  { id: 'liquid', label: 'Liquid names (1,840)', value: 0.941, display: '94.1%' },
  { id: 'rest', label: 'Rest (1,827)', value: 0.76, display: '76.0%' },
];

const funnel: BarListItem[] = [
  { id: 'universe', label: 'Universe (vrp_universe)', value: 4203 },
  { id: 'iv', label: 'Our IV30 ≥ 50%', value: 486 },
  { id: 'spread', label: 'IV − HV ≥ 10 pts', value: 212 },
  { id: 'ratio', label: 'IV / HV ≥ 1.25', value: 131 },
  { id: 'high-low', label: 'Near 52-week high or low', value: 52 },
  { id: 'price', label: 'Close > $5', value: 45 },
];

const meta = {
  title: 'Components/BarList',
  component: BarList,
  args: { items: tiers, label: 'By fetch priority', max: 1 },
} satisfies Meta<typeof BarList>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Coverage by fetch-priority tier: label | bar | share. */
export const Default: Story = {};

/** A screener funnel: label above each bar, counts at the end, scaled to the universe. */
export const Funnel: Story = {
  args: { items: funnel, label: 'Funnel (hard criteria)', layout: 'stacked', max: 4203 },
};

/** Per-row tones. */
export const Tones: Story = {
  args: {
    label: 'Quality checks by result',
    items: [
      { id: 'pass', label: 'Pass', value: 5, tone: 'positive' },
      { id: 'warn', label: 'Warn', value: 1, tone: 'warning' },
      { id: 'fail', label: 'Fail', value: 0, tone: 'negative' },
    ],
  },
};

/** Signed values around a zero axis: the mean return of each tenth of the ranked names. */
export const Diverging: Story = {
  args: {
    label: 'Mean return by decile',
    diverging: true,
    max: 0.09,
    format: { kind: 'delta', digits: 1 },
    items: [9, 6, 4, 2, 1, -0.5, -2, -3, -5, -7].map((v, i) => ({
      id: `d${i + 1}`,
      label: `Decile ${i + 1}`,
      value: v / 100,
    })),
  },
};

export const Loading: Story = { args: { loading: true } };

export const Empty: Story = { args: { items: [], emptyMessage: 'No hard criteria yet' } };

export const Error: Story = { args: { error: 'The funnel failed to compute' } };

export const Dense: Story = {
  args: {
    label: 'Top sectors',
    items: Array.from({ length: 10 }, (_, i) => ({
      id: `s${i}`,
      label: `Sector ${i + 1}`,
      value: 100 - i * 9,
    })),
  },
};
