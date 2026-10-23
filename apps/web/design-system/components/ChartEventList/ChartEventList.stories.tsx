import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import type { ChartEvent } from '../Chart';
import { ChartEventList } from './ChartEventList';

const SEC =
  'https://www.sec.gov/Archives/edgar/data/320193/000032019326000070/0000320193-26-000070-index.htm';
const SEC_2 =
  'https://www.sec.gov/Archives/edgar/data/320193/000032019326000071/0000320193-26-000071-index.htm';

const rows: ChartEvent[] = [
  {
    time: '2026-10-14',
    kind: 'macro',
    parts: [{ text: 'CPI 08:30 ET', href: 'https://www.bls.gov/cpi/' }],
  },
  { time: '2026-10-30', kind: 'earnings', parts: [{ text: 'Earnings after the close' }] },
  {
    time: '2026-08-14',
    kind: 'filing',
    parts: [
      { text: '8-K Results', href: SEC },
      { text: '8-K Management change', href: SEC_2 },
    ],
  },
  { time: '2026-07-30', kind: 'earnings', parts: [{ text: 'Reported', href: SEC }] },
  { time: '2026-05-11', kind: 'dividend', parts: [{ text: '$0.26 dividend' }] },
  { time: '2020-08-31', kind: 'split', parts: [{ text: '4-for-1 split' }] },
]; // fmt: skip

const meta = {
  title: 'Components/ChartEventList',
  component: ChartEventList,
  args: { label: 'AAPL events on the chart', events: rows },
} satisfies Meta<typeof ChartEventList>;

export default meta;
type Story = StoryObj<typeof meta>;

/** One row per marker, newest first; a source page is a link, otherwise plain text; two 8-Ks of one day are two links in one row. */
export const Default: Story = {};

export const Loading: Story = { args: { status: 'loading' } };

export const Empty: Story = { args: { events: [] } };

export const Error: Story = {
  args: {
    status: 'error',
    errorMessage: 'The events could not load for AAPL.',
    onRetry: () => undefined,
  },
};

/** A long window of one kind: many rows, one line each. */
export const Dense: Story = {
  args: {
    events: Array.from({ length: 24 }, (_, i) => ({
      time: `2026-${String(12 - Math.floor(i / 2)).padStart(2, '0')}-${i % 2 === 0 ? '10' : '25'}`,
      kind: 'macro' as const,
      parts: [{ text: i % 2 === 0 ? 'CPI 08:30 ET' : 'FOMC 14:00 ET' }],
    })),
  },
};

/** At phone width the description folds under the date and the letter. */
export const Narrow: Story = { ...Default, decorators: [narrow] };
