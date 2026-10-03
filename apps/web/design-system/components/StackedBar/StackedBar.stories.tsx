import type { Meta, StoryObj } from '@storybook/react-vite';

import { StackedBar, type StackedBarSegment } from './StackedBar';

const chains: StackedBarSegment[] = [
  { id: 'ok', label: 'OK', value: 3624, tone: 'positive' },
  { id: 'stale', label: 'Stale', value: 515, tone: 'warning' },
  { id: 'none', label: 'No chain', value: 63, tone: 'muted' },
  { id: 'non-standard', label: 'Non-standard', value: 2, tone: 'neutral' },
  { id: 'errors', label: 'Fetch errors', value: 0, tone: 'negative' },
];

const meta = {
  title: 'Components/StackedBar',
  component: StackedBar,
  args: { segments: chains, label: 'Option chains, Fri 2 Oct' },
} satisfies Meta<typeof StackedBar>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Option chains for one session: status segments and their counts. */
export const Default: Story = {};

/** Series tones: share of the screen's names by sector. */
export const Series: Story = {
  args: {
    label: 'Qualified names by sector',
    segments: [
      { id: 'tech', label: 'Technology', value: 6, tone: 's1' },
      { id: 'health', label: 'Health care', value: 3, tone: 's2' },
      { id: 'energy', label: 'Energy', value: 2, tone: 's3' },
      { id: 'fin', label: 'Financials', value: 2, tone: 's4' },
      { id: 'other', label: 'Other', value: 1, tone: 's5' },
    ],
  },
};

/** A total above the sum leaves the remainder as empty track. */
export const PartialTotal: Story = {
  args: {
    label: 'Chains fetched so far',
    total: 4203,
    segments: [
      { id: 'ok', label: 'OK', value: 2100, tone: 'positive' },
      { id: 'stale', label: 'Stale', value: 240, tone: 'warning' },
    ],
  },
};

export const Loading: Story = { args: { loading: true } };

export const Empty: Story = {
  args: { segments: [], emptyMessage: 'Chains are not collected for this session' },
};

export const Error: Story = { args: { error: 'Chain status failed to load' } };

export const Dense: Story = { args: { size: 'sm', showLegend: false } };
