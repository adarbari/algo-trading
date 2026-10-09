import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { narrow } from '../../testing';
import { Button } from '../Button';
import { KeyValue } from '../KeyValue';
import { Panel } from '../Panel';
import { MasterDetail, type MasterDetailProps } from './MasterDetail';

const TICKERS = ['AAPL', 'MSFT', 'NVDA', 'KO', 'SPY'] as const;

/** A ticker list beside the chosen ticker's detail; picking a row sets the key. */
function Example(props: Partial<MasterDetailProps> & { initial?: string | null }) {
  const [chosen, setChosen] = useState<string | null>(props.initial ?? null);
  const shown = chosen ?? TICKERS[0];
  return (
    <MasterDetail
      {...props}
      detailKey={chosen}
      detailTitle={shown}
      onDetailClose={() => {
        setChosen(null);
      }}
      master={
        <Panel title="Tickers">
          <Stack gap={1}>
            {TICKERS.map((ticker) => (
              <Button
                key={ticker}
                variant="ghost"
                onClick={() => {
                  setChosen(ticker);
                }}
              >
                {ticker}
              </Button>
            ))}
          </Stack>
        </Panel>
      }
      detail={
        <Panel title={`${shown} · overview`}>
          <KeyValue
            items={[
              { label: 'Last close', value: 333.69, format: { kind: 'currency' } },
              { label: 'IV30', value: 0.244, format: { kind: 'percent' } },
              { label: 'Next earnings', value: '19 sessions' },
            ]}
          />
        </Panel>
      }
    />
  );
}

const meta = {
  title: 'Components/MasterDetail',
  component: MasterDetail,
  args: {
    master: null,
    detail: null,
    detailKey: null,
    detailTitle: '',
    onDetailClose: () => undefined,
  },
  render: (args) => <Example {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a layout; the master and the detail show their own loading state',
        Empty: 'a layout; the master shows its own empty state',
        Error: 'a layout; the master and the detail show their own error state',
        Dense: 'a layout; its children follow the density tokens',
      },
    },
  },
} satisfies Meta<typeof MasterDetail>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Wide: the list and the detail side by side. */
export const Default: Story = {};

/** `main-aside` columns with a summary at the top of the detail column. */
export const MainAside: Story = {
  args: { columns: 'main-aside' },
  render: (args) => (
    <Example
      {...args}

      summary={<Text size="sm">Compare: AAPL, MSFT</Text>}
    />
  ),
};

/** Phone width: the summary above the list, the chosen ticker's detail in a side sheet. */
export const Narrow: Story = {
  decorators: [narrow],
  render: (args) => (
    <Example
      {...args}

      initial="NVDA"
      summary={<Text size="sm">Compare: AAPL, MSFT</Text>}
    />
  ),
};

/** Phone width with previous / next in the header and the item's actions pinned to the bottom. */
export const NarrowSheet: Story = {
  decorators: [narrow],
  render: (args) => (
    <Example
      {...args}
      initial="MSFT"
      step={{
        onPrevious: () => undefined,
        onNext: () => undefined,
        hasPrevious: true,
        hasNext: true,
      }}
      detailFooter={
        <>
          <Button size="sm">Open in Explore</Button>
          <Button size="sm" variant="secondary">
            Compare
          </Button>
          <Button size="sm" variant="ghost">
            Dismiss
          </Button>
        </>
      }
    />
  ),
};
