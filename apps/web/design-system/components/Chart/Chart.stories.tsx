import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { expect, userEvent, waitFor, within } from 'storybook/test';

import { SegmentedControl } from '../SegmentedControl';
import { Chart, type ChartProps } from './Chart';
import { CHART_RANGES, type ChartRange } from './chartData';
import {
  aapl,
  aaplEvents,
  aaplVolume,
  aaplWithGap,
  eventMarkers,
  hatchedBand,
  msft,
  nvda,
  sampleBands,
  sampleLanes,
  sampleReferenceLines,
  sampleValueBands,
} from './storyData';

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

/**
 * Event markers of the event-sensitivity price chart: earnings (up arrow, E), filings (down
 * arrow, F) and macro releases (circle, M), keyed under the chart, with the marker's text in the
 * hover read-out. Sample data.
 */
export const WithEventMarkers: Story = { args: { events: eventMarkers } };

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
    volume: aaplVolume.map((p) => ({ ...p, value: (p.value ?? 0) * 10 })),
    range: '1Y',
    height: 'lg',
  },
};

/**
 * With bands: shaded spans behind the line (a market regime, a drawdown), keyed under the chart
 * and listed for screen readers. Two bands touch on 20 / 21 Feb. Sample data.
 */
export const WithBands: Story = { args: { bands: sampleBands, events: aaplEvents } };

/**
 * With reference lines: horizontal lines across the price pane with their label at the right end
 * (a floor dashed in the negative tone, a target solid in the positive one). Sample data.
 */
export const WithReferenceLines: Story = {
  args: { referenceLines: sampleReferenceLines, range: '1Y' },
};

/**
 * With a value band: a span of values shaded across the price pane (here everything under the
 * floor, open below), named in the key and kept inside the axis. Sample data.
 */
export const WithValueBand: Story = {
  args: { valueBands: sampleValueBands, referenceLines: sampleReferenceLines, range: '1Y' },
};

/**
 * With lanes and bands: thin strips under the price pane on the chart's own time scale (the
 * crosshair names the span under it), shaded bands behind the line and a hatched band that
 * overlaps two of them; all named in the key. Sample data.
 */
export const WithLanesAndBands: Story = {
  args: {
    bands: [...sampleBands, hatchedBand],
    lanes: sampleLanes,
    referenceLines: sampleReferenceLines,
    range: '1Y',
    height: 'lg',
  },
};

/** A missing stretch (null values): the line breaks instead of drawing a zero or joining. */
export const WithGap: Story = { args: { series: [aaplWithGap], range: '1Y' } };

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
