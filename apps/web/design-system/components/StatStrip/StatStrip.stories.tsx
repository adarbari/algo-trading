import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { StatStrip, type StatItem } from './StatStrip';

const summary: StatItem[] = [
  {
    label: 'Completeness · Fri 2 Oct',
    value: 0.964,
    format: { kind: 'percent' },
    sub: 'of expected rows across 13 datasets',
  },
  {
    label: 'Quality checks',
    value: '5 pass · 1 warn',
    tone: 'warning',
    sub: 'stale option chains 12.3% (warn above 20%)',
  },
  { label: 'Run', value: '1h 21m', sub: 'alert at 2h 30m · chains 93% of time' },
  {
    label: 'Open issues',
    value: 3,
    format: { kind: 'number' },
    sub: '2 FIGI reviews · 21 leveraged ETFs to curate',
  },
];

const meta = {
  title: 'Components/StatStrip',
  component: StatStrip,
  args: { items: summary, label: 'Summary' },
} satisfies Meta<typeof StatStrip>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The ingestion summary: four stats in one strip, divided by borders. */
export const Default: Story = {};

export const Loading: Story = { args: { loading: true } };

export const Empty: Story = {
  args: { items: [], emptyMessage: 'No run recorded for this session yet' },
};

export const Error: Story = {
  args: { error: 'The run summary failed to load. Retry from the run record.' },
};

/** Signed changes carry their up / down tone. */
export const Tones: Story = {
  args: {
    label: 'Portfolio',
    items: [
      { label: 'Day change', value: 0.0124, format: { kind: 'delta' }, sub: 'vs Thu close' },
      { label: 'Week change', value: -0.0087, format: { kind: 'delta' }, sub: 'vs last Fri' },
      {
        label: 'Premium collected',
        value: 13_990,
        format: { kind: 'currency', digits: 0 },
        sub: '14 positions',
      },
    ],
  },
};

/** Two stats, no sub-lines: the compact form under a page title. */
export const Dense: Story = {
  args: {
    items: [
      { label: 'Qualified', value: 14, format: { kind: 'number' } },
      { label: 'Watch', value: 22, format: { kind: 'number' } },
      { label: 'Event risk', value: 9, format: { kind: 'number' }, tone: 'warning' },
    ],
  },
};

/** Nine stats (the Financials key metrics): one row from 1200 px, three to a row below it. */
export const Many: Story = {
  args: {
    label: 'Key financials',
    items: [
      { label: 'P/E ratio', value: 24.3, format: { kind: 'number' } },
      { label: 'Forward P/E', value: 21.8, format: { kind: 'number' } },
      { label: 'Revenue growth (YoY)', value: 0.061, format: { kind: 'delta' } },
      { label: 'Forward revenue growth', value: 0.048, format: { kind: 'delta' } },
      { label: 'EPS growth (YoY)', value: 0.093, format: { kind: 'delta' } },
      { label: 'Operating margin', value: 0.294, format: { kind: 'percent' } },
      { label: 'Debt to equity', value: 1.8, format: { kind: 'number' } },
      { label: 'Free cash flow', value: 9.1e9, format: { kind: 'currency-compact' } },
      { label: 'Last EPS surprise', value: 0.047, format: { kind: 'delta' } },
    ],
  },
};

/** Nine stats in a phone-width container (375 px): two to a row, not nine stacked. */
export const NarrowMany: Story = { ...Many, decorators: [narrow] };

/** A phone-width container (375 px): the stats stack in one column. */
export const Narrow: Story = { decorators: [narrow] };
