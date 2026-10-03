import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { TickerTag } from './TickerTag';

const meta = {
  title: 'Components/TickerTag',
  component: TickerTag,
  args: { symbol: 'AAPL', series: 's1', name: 'Apple Inc.' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a tag shows a symbol already known; nothing loads',
        Error: 'a tag cannot fail; an unknown ticker is never tagged',
      },
    },
  },
} satisfies Meta<typeof TickerTag>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** The compare list: one tag per series slot, removable. */
export const Compare: Story = {
  render: () => (
    <Stack direction="row" gap={1.5} align="center" wrap>
      <Text size="sm" tone="muted">
        Comparing
      </Text>
      {(['s1', 's2', 's3', 's4', 's5', 's6'] as const).map((series, i) => (
        <TickerTag
          key={series}
          series={series}
          symbol={['AAPL', 'MSFT', 'NVDA', 'SPY', 'QQQ', 'KO'][i] ?? ''}
          onRemove={() => undefined}
          removeContext="from compare"
        />
      ))}
    </Stack>
  ),
};

export const Neutral: Story = { render: () => <TickerTag symbol="JPM" name="JPMorgan Chase" /> };

/** Nothing selected yet. */
export const Empty: Story = {
  render: () => (
    <Text size="sm" tone="muted">
      Select tickers in the list to compare them.
    </Text>
  ),
};

/** Many tags wrapping. */
export const Dense: Story = {
  render: () => (
    <Stack direction="row" gap={1} wrap>
      {['AAPL', 'MSFT', 'NVDA', 'SPY', 'QQQ', 'KO', 'TSLA', 'JPM', 'XLE', 'IWM'].map((s) => (
        <TickerTag key={s} symbol={s} />
      ))}
    </Stack>
  ),
};
