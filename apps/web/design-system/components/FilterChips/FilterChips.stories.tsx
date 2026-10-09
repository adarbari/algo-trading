import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import { FilterChips, type FilterValues } from './FilterChips';

const FILTERS = [
  {
    id: 'screener',
    label: 'Screener',
    options: [
      { value: 'vrp', label: 'VRP scanner' },
      { value: 'mr', label: 'Mean reversion' },
    ],
  },
  {
    id: 'liq',
    label: 'Liquidity',
    options: [
      { value: 'high', label: 'High' },
      { value: 'low', label: 'Low' },
    ],
  },
  {
    id: 'regime',
    label: 'Regime',
    options: [{ value: 'clouds', label: 'Clouds building' }],
  },
];

function Held({ initial = {} }: { initial?: FilterValues }) {
  const [values, setValues] = useState<FilterValues>(initial);
  return (
    <FilterChips
      filters={FILTERS}
      values={values}
      onChange={(id, value) => {
        setValues((previous) => ({ ...previous, [id]: value }));
      }}
      onClear={() => {
        setValues({});
      }}
    />
  );
}

const meta = {
  title: 'Components/FilterChips',
  component: FilterChips,
  args: { filters: FILTERS, values: {}, onChange: () => undefined, onClear: () => undefined },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the filters are given; nothing loads here',
        Error: 'the filters are given; nothing can fail here',
      },
    },
  },
} satisfies Meta<typeof FilterChips>;

export default meta;
type Story = StoryObj<typeof meta>;

/** No filter in force: only the dashed add buttons. */
export const Default: Story = { render: () => <Held /> };

/** Two in force: removable chips, the rest to add, and Clear filters. */
export const Empty: Story = {
  render: () => <Held initial={{ screener: 'vrp', liq: 'low' }} />,
};

/** Every filter in force at once. */
export const Dense: Story = {
  render: () => <Held initial={{ screener: 'vrp', liq: 'low', regime: 'clouds' }} />,
};

/** A 375 px phone frame: the chips wrap, never scroll the page sideways. */
export const Narrow: Story = { ...Dense, decorators: [narrow] };
