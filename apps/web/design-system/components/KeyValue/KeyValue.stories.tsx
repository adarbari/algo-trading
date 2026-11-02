import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { InfoButton } from '../InfoButton';
import { KeyValue, type KeyValueItem } from './KeyValue';

const ticker: KeyValueItem[] = [
  { label: 'Last close', hint: 'price_stats.close', value: 333.69, format: { kind: 'currency' } },
  { label: 'IV30 (ours)', hint: 'iv30.iv30', value: 0.244, format: { kind: 'percent' } },
  { label: 'HV30', hint: 'price_stats.hv30', value: 0.212, format: { kind: 'percent' } },
  { label: 'IV − HV', hint: 'iv_hv_spread', value: 3.2, format: { kind: 'delta', unit: 'points' } },
  { label: 'From 52w high', hint: 'pct_from_high_52w', value: -0.034, format: { kind: 'delta' } },
  {
    label: 'Avg dollar volume 20d',
    hint: 'price_stats.adv_usd_20d',
    value: 13_990_000_000,
    format: { kind: 'currency-compact' },
  },
  {
    label: 'Market cap',
    hint: 'market_cap',
    value: 4_870_000_000_000,
    format: { kind: 'currency-compact' },
  },
  { label: 'Next earnings', hint: 'earnings.days_to_earnings', value: '19 sessions' },
  { label: 'Dividend yield', hint: 'div_yield', value: null, format: { kind: 'percent' } },
];

const meta = {
  title: 'Components/KeyValue',
  component: KeyValue,
  args: { items: ticker, label: 'AAPL details', alignValues: 'end' },
  parameters: {
    states: {
      notApplicable: {
        Error: 'a detail list shows values it is given; a failed load is the panel error state',
      },
    },
  },
} satisfies Meta<typeof KeyValue>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A ticker's details: label + feature id, formatted values with up / down tones. */
export const Default: Story = {};

export const Loading: Story = { args: { loading: true } };

export const Empty: Story = {
  args: { items: [], emptyMessage: 'Select a ticker to see its details' },
};

/** Run record: label above value, monospace ids. */
export const Stacked: Story = {
  args: {
    layout: 'stacked',
    alignValues: 'start',
    items: [
      { label: 'Run', value: 'nightly-2026-10-02-1500', mono: true },
      { label: 'Session', value: '2026-10-02', format: { kind: 'date', style: 'weekday' } },
      { label: 'Duration', value: '1h 21m' },
    ],
  },
};

/** Grid: a setup's rules or a pick's plan, a fixed label column and no row rules. */
export const Grid: Story = {
  args: {
    layout: 'grid',
    items: [
      { label: 'Entry', value: 'Mon 26 Oct, at the close' },
      { label: 'Stop', value: 'About $296.16, 5.2% under entry' },
      { label: 'Exit', value: 'At the close on Mon 23 Nov, 20 sessions later' },
    ],
  },
};

export const GridNarrow: Story = { ...Grid, decorators: [narrow] };

export const Dense: Story = {
  args: {
    items: ticker.slice(0, 4).map(({ hint: _hint, ...item }) => item),
  },
};

const withActions: KeyValueItem[] = [
  {
    label: 'Revenue',
    hint: 'financials.revenue',
    value: 391_000_000_000,
    format: { kind: 'currency-compact' },
    action: <InfoButton label="About Revenue" onClick={() => undefined} />,
  },
  {
    label: 'Net margin',
    value: 0.24,
    format: { kind: 'percent' },
    action: <InfoButton label="About Net margin" onClick={() => undefined} />,
  },
  { label: 'Free cash flow', value: 99_000_000_000, format: { kind: 'currency-compact' } },
];

/** A help button beside a label; rows without one are unchanged. */
export const WithAction: Story = { args: { items: withActions } };

/** In a narrow container the action wraps under a long label instead of overflowing. */
export const Narrow: Story = {
  args: { items: withActions },
  decorators: [narrow],
};
