import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { OptionList, type OptionListItem, type OptionListProps } from './OptionList';

const fields: OptionListItem[] = [
  {
    id: 'bb_width_pctile_252d',
    title: 'bb_width_pctile_252d',
    description: 'Where the bands’ width sits against the name’s own last year: low is a squeeze.',
  },
  { id: 'bb_squeeze', title: 'bb_squeeze', description: 'Bands inside the Keltner channel.' },
  {
    id: 'atr_ratio_5_20',
    title: 'atr_ratio_5_20',
    description: 'Short-term range against the 20-day range.',
  },
  { id: 'hv20_pctile_252d', title: 'hv20_pctile_252d', description: 'Realised volatility rank.' },
];

/** The list with the caller's choice, as screens use it. */
function Chosen(props: OptionListProps) {
  const [value, setValue] = useState<string | null>(props.value);
  return <OptionList {...props} value={value} onSelect={setValue} />;
}

const meta = {
  title: 'Components/OptionList',
  component: OptionList,
  args: {
    items: fields,
    value: 'bb_squeeze',
    onSelect: () => undefined,
    label: 'Fields',
    mono: true,
  },
  render: (args) => <Chosen {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Error: 'a list shows the items it is given; its parent shows a failed load',
      },
    },
  },
} satisfies Meta<typeof OptionList>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Monospace names over a one-line meaning; the current choice in the accent tint. */
export const Default: Story = {};

/** Taller than `maxHeight`: the list scrolls inside itself. */
export const Scrolling: Story = {
  args: {
    maxHeight: 'md',
    items: [...fields, ...fields, ...fields].map((f, i) => ({ ...f, id: `${f.id}-${String(i)}` })),
    value: null,
  },
};

export const Loading: Story = { args: { loading: true } };

export const Empty: Story = { args: { items: [], emptyMessage: 'No field matches “squeeze”.' } };

/** Names only, plain face. */
export const Dense: Story = {
  args: {
    mono: false,
    items: fields.map(({ id, title }) => ({ id, title })),
  },
};
