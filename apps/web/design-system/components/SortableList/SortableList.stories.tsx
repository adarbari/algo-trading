import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Text } from '../../primitives/Text';
import { EmptyState } from '../EmptyState';
import { SortableList, type SortableListProps } from './SortableList';

interface Rule {
  id: string;
  name: string;
  detail: string;
}

const RULES: Rule[] = [
  { id: 'liq', name: 'Liquidity', detail: 'Average volume above 1M' },
  { id: 'iv', name: 'IV rank', detail: 'Above 50 over 52 weeks' },
  { id: 'earn', name: 'Earnings', detail: 'None within 7 days' },
  { id: 'trend', name: 'Trend', detail: 'Close above the 50-day average' },
];

/** Holds the order, as the owning page would. */
function Stateful(props: Partial<SortableListProps<Rule>>) {
  const [items, setItems] = useState<readonly Rule[]>(props.items ?? RULES);
  return (
    <SortableList<Rule>
      label="Screener priority"
      getKey={(rule) => rule.id}
      getLabel={(rule) => rule.name}
      renderItem={(rule) => (
        <>
          <Text size="base">{rule.name}</Text>{' '}
          <Text size="sm" tone="muted">
            {rule.detail}
          </Text>
        </>
      )}
      {...props}
      items={items}
      onReorder={setItems}
    />
  );
}

const meta = {
  title: 'Components/SortableList',
  component: Stateful,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a sortable list orders items it is given; its parent shows loading',
        Error: 'a sortable list holds no data of its own; its parent shows a failed load',
        Dense: 'rows take the density control height from the theme, like every control',
      },
    },
  },
} satisfies Meta<typeof Stateful>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Drag a handle, or focus it and press Space. */
export const Default: Story = {};

/** Mid-drag with the pointer: the held row is lifted and already in its new place. */
export const Dragging: Story = {
  play: async ({ canvasElement }) => {
    const handle = canvasElement.querySelectorAll<HTMLElement>('button')[1];
    handle?.dispatchEvent(
      new PointerEvent('pointerdown', { bubbles: true, button: 0, clientX: 20, clientY: 60 }),
    );
    await Promise.resolve();
  },
};

/** Grabbed from the keyboard and moved one place down. */
export const KeyboardGrabbed: Story = {
  play: async ({ canvasElement }) => {
    const handle = canvasElement.querySelectorAll<HTMLElement>('button')[0];
    handle?.focus();
    const press = (key: string) =>
      handle?.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    press(' ');
    await Promise.resolve();
    press('ArrowDown');
    await Promise.resolve();
  },
};

export const Disabled: Story = { args: { disabled: true } };

export const Empty: Story = {
  args: {
    items: [],
    empty: (
      <EmptyState
        compact
        title="No criteria yet"
        description="Add a criterion to set the priority order."
      />
    ),
  },
};
