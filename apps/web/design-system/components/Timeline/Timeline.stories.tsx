import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { narrow } from '../../testing';
import { Legend } from '../Legend';
import { Timeline, type TimelineRow } from './Timeline';

/** Sample rows: days from an event (0), some before it, one still going, one late, one never. */
const ROWS: TimelineRow[] = [
  {
    id: 'a',
    label: 'Credit spreads',
    spans: [{ id: 'a', from: -40, to: 25, tone: 's2', label: 'On' }],
    markers: [{ id: 'a', at: -40, tone: 's2', label: 'Flagged' }],
  },
  {
    id: 'b',
    label: 'Trend break',
    spans: [{ id: 'b', from: -5, to: null, tone: 's1', label: 'On' }],
    markers: [{ id: 'b', at: -5, tone: 's1', label: 'Flagged' }],
  },
  {
    id: 'c',
    label: 'Volatility term',
    note: 'Late',
    spans: [{ id: 'c', from: 30, to: 60, tone: 's1', variant: 'outline', label: 'On' }],
    markers: [{ id: 'c', at: 30, tone: 's1', hollow: true, label: 'Flagged' }],
  },
  {
    id: 'd',
    label: 'Breadth',
    note: 'Known from day -10',
    spans: [{ id: 'd', from: -10, to: 12, tone: 's1', openStart: true, label: 'On' }],
  },
  { id: 'e', label: 'Sahm rule', note: 'Never fired' },
  { id: 'f', label: 'Yield curve', note: 'Unknown: no verdict stored' },
  {
    id: 'g',
    label: 'Screener gate',
    markers: [{ id: 'g', at: 8, tone: 'neutral', shape: 'diamond', label: 'Shut' }],
  },
];

const meta = {
  title: 'Components/Timeline',
  component: Timeline,
  args: {
    rows: ROWS,
    label: 'When each warning sign flagged',
    reference: { at: 0, label: 'the peak' },
    axisLabel: 'Sessions from the peak',
  },
} satisfies Meta<typeof Timeline>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Bars from the first day on to the first day off; one still on; one late (hollow); a gap. */
export const Default: Story = {};

/** Placeholder rows. */
export const Loading: Story = { args: { loading: true } };

/** No rows. */
export const Empty: Story = { args: { rows: [], emptyMessage: 'No signals are stored.' } };

/** A failed load replaces the rows. */
export const Error: Story = { args: { error: 'The timing failed to load.' } };

/** Many short rows at the compact height, markers only (an overview). */
export const Dense: Story = {
  args: {
    size: 'sm',
    rows: Array.from({ length: 12 }, (_, i) => ({
      id: `r${String(i)}`,
      label: `Episode ${String(i + 1)}`,
      markers: [
        { id: 'x', at: -60 + i * 9, tone: 's1' as const, label: 'Fast' },
        { id: 'y', at: -90 + i * 11, tone: 's2' as const, label: 'Slow' },
        {
          id: 'z',
          at: -20 + i * 5,
          tone: 'neutral' as const,
          shape: 'diamond' as const,
          label: 'Gate',
        },
      ],
    })),
  },
};

/** A shared domain lines two timelines up, with a key that is not colour alone. */
export const WithKey: Story = {
  render: (args) => (
    <Stack gap={2}>
      <Legend
        label="Signal kinds"
        items={[
          { label: 'Fast', tone: 's1' },
          { label: 'Slow', tone: 's2' },
          { label: 'Gate (diamond)', tone: 'neutral' },
        ]}
      />
      <Timeline {...args} domain={{ min: -100, max: 100 }} />
    </Stack>
  ),
};

/** A phone (375 px): each name above its marks. */
export const Narrow: Story = { decorators: [narrow] };
