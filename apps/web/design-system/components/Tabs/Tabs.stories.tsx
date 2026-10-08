import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Text } from '../../primitives/Text';
import { Tabs, type TabItem, type TabsProps } from './Tabs';
import { narrow } from '../../testing';

const views: TabItem[] = [
  { id: 'compare', label: 'Compare' },
  { id: 'chart', label: 'Chart' },
  { id: 'options', label: 'Options' },
  { id: 'features', label: 'Features' },
  { id: 'events', label: 'Events' },
  { id: 'ideas', label: 'Screener hits' },
];

/** Stories own the selected tab (the component is controlled). */
function Controlled(props: Omit<TabsProps, 'value' | 'onChange'> & { initial: string }) {
  const { initial, ...rest } = props;
  const [value, setValue] = useState(initial);
  return (
    <Tabs {...rest} value={value} onChange={setValue}>
      {rest.children === undefined ? undefined : <Text tone="secondary">View: {value}</Text>}
    </Tabs>
  );
}

const meta = {
  title: 'Components/Tabs',
  component: Tabs,
  args: { items: views, value: 'compare', label: 'View', onChange: () => undefined },
  render: (args) => (
    <Controlled items={args.items} label={args.label} initial={args.value} size={args.size ?? 'md'}>
      panel
    </Controlled>
  ),
  parameters: {
    states: {
      notApplicable: {
        Loading: 'tabs are static navigation; the selected panel shows its own loading state',
        Empty: 'a tab list with no tabs is not rendered; each panel shows its own empty state',
        Error: 'tabs hold no data; the selected panel shows its own error state',
      },
    },
  },
} satisfies Meta<typeof Tabs>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The Explore views: underline tabs and the selected panel. */
export const Default: Story = {};

/** Counts after labels; a disabled tab is skipped by the arrow keys. */
export const CountsAndDisabled: Story = {
  args: {
    value: 'qualified',
    label: 'Decision',
    items: [
      { id: 'qualified', label: 'Qualified', count: 14 },
      { id: 'watch', label: 'Watch', count: 22 },
      { id: 'event', label: 'Event risk', count: 9 },
      { id: 'unknown', label: 'Unknown', count: 0, disabled: true },
    ],
  },
};

/** Small tabs in a dense toolbar. */
export const Dense: Story = { args: { size: 'sm' } };

/** A 375 px phone frame; under a coarse pointer the control floors apply. */
export const Narrow: Story = { ...Dense, decorators: [narrow] };
