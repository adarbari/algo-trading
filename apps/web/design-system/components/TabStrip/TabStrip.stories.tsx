import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Text } from '../../primitives/Text';
import { narrow } from '../../testing';
import { TabStrip, type TabStripItem, type TabStripProps } from './TabStrip';

const item = (id: string): TabStripItem => ({
  id,
  label: id,
  closeLabel: `Close ${id}`,
  mono: true,
});
const FEW = ['NVDA', 'AAPL', 'SPY'].map(item);
const MANY = ['NVDA', 'AAPL', 'SPY', 'SMCI', 'SMH', 'MSFT', 'XOM', 'JPM', 'KO', 'PEP'].map(item);

/** Stories own the list and the selection (the component is controlled). */
function Controlled({
  items,
  value,
  closable = true,
}: {
  items: TabStripItem[];
  value: string | null;
  closable?: boolean;
}) {
  const [open, setOpen] = useState(items);
  const [current, setCurrent] = useState(value);
  const props: TabStripProps = {
    items: open,
    value: current,
    label: 'Open items',
    onChange: setCurrent,
    ...(closable
      ? {
          onClose: (id: string) => {
            setOpen((all) => all.filter((i) => i.id !== id));
            if (id === current) setCurrent(open.find((i) => i.id !== id)?.id ?? null);
          },
        }
      : {}),
  };
  return (
    <TabStrip {...props}>
      <Text tone="secondary">Content of {current}</Text>
    </TabStrip>
  );
}

const meta = {
  title: 'Components/TabStrip',
  component: TabStrip,
  args: { items: FEW, value: 'NVDA', label: 'Open items', onChange: () => undefined },
  render: (args) => <Controlled items={[...args.items]} value={args.value} />,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a tab strip holds no data; the selected panel shows its own loading state',
        Empty: 'see NoneOpen: with no items only the caller shows its empty state',
        Error: 'a tab strip holds no data; the selected panel shows its own error state',
      },
    },
  },
} satisfies Meta<typeof TabStrip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** More tabs than fit: the row scrolls sideways and keeps the selected one in view. */
export const Dense: Story = { args: { items: MANY, value: 'PEP' } };

/** Nothing open: no tab is selected and no panel is drawn. */
export const NoneOpen: Story = { args: { items: [], value: null } };

export const NotClosable: Story = {
  render: (args) => <Controlled items={[...args.items]} value={args.value} closable={false} />,
};

export const Narrow: Story = { ...Dense, decorators: [narrow] };
