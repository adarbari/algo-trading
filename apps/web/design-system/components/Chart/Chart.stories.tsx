import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { expect, userEvent, waitFor, within } from 'storybook/test';

import { SegmentedControl } from '../SegmentedControl';
import { Chart, type ChartProps } from './Chart';
import { CHART_RANGES, type ChartRange } from './chartData';
import { aapl, aaplEvents, aaplVolume, msft, nvda } from './storyData';

/** The chart with the caller's range control, as screens use it. */
function WithRange(props: ChartProps) {
  const [range, setRange] = useState<ChartRange>(props.range ?? '1Y');
  return (
    <Chart
      {...props}
      range={range}
      toolbar={
        <SegmentedControl
          aria-label="Time range"
          size="sm"
          options={CHART_RANGES.map((r) => ({ value: r, label: r }))}
          value={range}
          onValueChange={setRange}
        />
      }
    />
  );
}

/** Screenshots wait until the canvas has painted (fonts loaded, two frames after the draw). */
const painted = async ({ canvasElement }: { canvasElement: HTMLElement }) => {
  await waitFor(
    () => {
      void expect(canvasElement.querySelector('[data-ready]')).not.toBeNull();
    },
    { timeout: 5000 },
  );
};

const meta = {
  title: 'Components/Chart',
  component: Chart,
  args: { label: 'AAPL close', series: [aapl], range: '1Y' },
  render: (args) => <WithRange {...args} />,
  play: painted,
} satisfies Meta<typeof Chart>;

export default meta;
type Story = StoryObj<typeof meta>;

/** One price series with its ex-dividend, split and earnings markers. Sample data. */
export const Default: Story = { args: { events: aaplEvents } };

/** The Explore compare chart: three tickers rebased to 100 over the window. */
export const Compare: Story = {
  args: { label: 'AAPL, MSFT and NVDA', series: [aapl, msft, nvda], rebase: true },
};

/** A single area series with a volume pane, two years. */
export const WithVolume: Story = {
  args: { type: 'area', volume: aaplVolume, range: '2Y', height: 'lg' },
};

/** Hundreds of millions of shares: the volume axis reads 800M, the price axis stays currency. */
export const WithLargeVolume: Story = {
  args: {
    volume: aaplVolume.map((p) => ({ ...p, value: p.value * 10 })),
    range: '1Y',
    height: 'lg',
  },
};

/** The table fallback: the same numbers in a DataTable. */
export const TableView: Story = {
  args: { label: 'AAPL, MSFT and NVDA', series: [aapl, msft, nvda], rebase: true, range: '3M' },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: 'View as table' }));
    await expect(within(canvasElement).getByRole('grid')).toBeInTheDocument();
  },
};

export const Loading: Story = { args: { status: 'loading' }, play: () => undefined };

export const Empty: Story = {
  args: { series: [{ id: 'X', label: 'XMAX', points: [] }] },
  play: () => undefined,
};

export const Error: Story = {
  args: {
    status: 'error',
    errorMessage: 'Price history could not load.',
    onRetry: () => undefined,
  },
  play: () => undefined,
};

/** Small, three months, no table switch: a chart inside a detail panel. */
export const Dense: Story = {
  args: { height: 'sm', range: '3M', tableView: false, events: aaplEvents },
};
