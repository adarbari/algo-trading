import type { Meta, StoryObj } from '@storybook/react-vite';

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

export const Dense: Story = {
  args: {
    items: ticker.slice(0, 4).map(({ hint: _hint, ...item }) => item),
  },
};
