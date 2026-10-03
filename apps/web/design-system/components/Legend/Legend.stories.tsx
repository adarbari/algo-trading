import type { Meta, StoryObj } from '@storybook/react-vite';

import { Legend } from './Legend';

const meta = {
  title: 'Components/Legend',
  component: Legend,
  args: {
    label: 'Status key',
    swatch: 'cell',
    items: [
      { label: 'complete', tone: 'positive' },
      { label: 'partial', tone: 'warning' },
      { label: 'failed', tone: 'negative' },
      { label: 'not collected', tone: 'empty' },
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a legend is static text next to its chart; the chart shows the loading state',
        Empty: 'a legend with no items is not rendered by its caller (nothing to explain)',
        Error: 'a legend has no data of its own to fail; the chart shows the error state',
      },
    },
  },
} satisfies Meta<typeof Legend>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Status tones as tinted cells: the key of the ingestion completeness grid. */
export const Default: Story = {};

/** The six data series in their fixed order. */
export const Series: Story = {
  args: {
    label: 'Series',
    swatch: 'line',
    items: [
      { label: 'AAPL', tone: 's1' },
      { label: 'MSFT', tone: 's2' },
      { label: 'NVDA', tone: 's3' },
      { label: 'SPY', tone: 's4' },
      { label: 'QQQ', tone: 's5' },
      { label: 'TSLA', tone: 's6' },
    ],
  },
};

/** Solid swatches with values: the key under a stacked bar. */
export const WithValues: Story = {
  args: {
    label: 'Option chains',
    swatch: 'solid',
    items: [
      { label: 'OK', tone: 'positive', value: '3,624' },
      { label: 'Stale', tone: 'warning', value: '515' },
      { label: 'No chain', tone: 'muted', value: '63' },
      { label: 'Fetch errors', tone: 'negative', value: '0' },
    ],
  },
};

export const Dense: Story = {
  args: { size: 'xs' },
};
