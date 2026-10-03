import type { Meta, StoryObj } from '@storybook/react-vite';

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
