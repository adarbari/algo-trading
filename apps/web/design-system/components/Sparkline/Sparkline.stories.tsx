import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Sparkline } from './Sparkline';

const rising = [21.2, 21.8, 21.1, 22.4, 23.0, 22.6, 23.4, 24.1, 23.7, 24.4];
const falling = [44.1, 43.0, 43.6, 41.2, 40.8, 41.5, 39.9, 38.2, 38.8, 37.6];

const meta = {
  title: 'Components/Sparkline',
  component: Sparkline,
  args: {
    values: rising,
    label: 'AAPL IV30, 10 sessions',
    format: { kind: 'number', digits: 1 },
  },
  parameters: {
    states: {
      notApplicable: {
        Error: 'a sparkline sits in a cell; a failed load is the table or panel error state',
      },
    },
  },
} satisfies Meta<typeof Sparkline>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Rising: drawn in the up colour (tone `auto`), last value marked. */
export const Default: Story = { args: { showLast: true } };

/** Falling, in the down colour. */
export const Falling: Story = { args: { values: falling, label: 'TSLA IV30, 10 sessions' } };

/** Series colours for a compare list, and a dashed baseline at 100 for rebased values. */
export const SeriesAndBaseline: Story = {
  render: () => (
    <Stack gap={2}>
      {(['s1', 's2', 's3'] as const).map((tone, i) => (
        <Stack key={tone} direction="row" gap={3} align="center">
          <Text mono size="sm">
            {['AAPL', 'MSFT', 'NVDA'][i]}
          </Text>
          <Sparkline
            tone={tone}
            baseline={100}
            width="lg"
            label={`${['AAPL', 'MSFT', 'NVDA'][i] ?? ''} rebased`}
            values={[100, 98 + i, 103 - i, 101 + i * 2, 99, 104 + i * 3, 106 - i, 108 + i * 4]}
          />
        </Stack>
      ))}
    </Stack>
  ),
};

/** A gap (missing value) breaks the line. */
export const WithGap: Story = {
  args: { values: [21.2, 21.8, null, null, 23.0, 22.6, 23.4, 24.1], label: 'IV30 with gaps' },
};

export const Loading: Story = { args: { loading: true } };

/** Fewer than two values: a muted dash. */
export const Empty: Story = { args: { values: [24.4] } };

/** The small width, in a dense list. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      {[rising, falling, rising.toReversed(), falling.toReversed()].map((values, i) => (
        <Stack key={i} direction="row" gap={2} align="center">
          <Text mono size="sm">
            {['AAPL', 'TSLA', 'KO', 'JPM'][i]}
          </Text>
          <Sparkline width="sm" values={values} label={`Row ${String(i + 1)}`} />
        </Stack>
      ))}
    </Stack>
  ),
};
