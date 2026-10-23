import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import {
  FilterChips,
  type FilterChipItem,
  type FilterValues,
  type LegacyFilterChipsProps,
} from './FilterChips';

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

const ITEMS: FilterChipItem[] = [
  { id: 'decision', label: 'Decision', valueText: 'Qualified, Watch', removes: 212, active: true },
  { id: 'dte', label: 'DTE', valueText: '..14', removes: 96, unknown: 4, active: true },
  { id: 'liq', label: 'Liquidity', valueText: 'risk', removes: 31, active: false },
];

/** The structured form with the caller's items. */
function Applied({ initial = ITEMS }: { initial?: FilterChipItem[] }) {
  const [items, setItems] = useState(initial);
  return (
    <FilterChips
      items={items}
      onToggle={(id) => {
        setItems((now) => now.map((i) => (i.id === id ? { ...i, active: !i.active } : i)));
      }}
      onRemove={(id) => {
        setItems((now) => now.filter((i) => i.id !== id));
      }}
      onClear={() => {
        setItems([]);
      }}
    />
  );
}

const meta: Meta<LegacyFilterChipsProps> = {
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
};

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

/** Structured chips (ADR 0082): "removes N", an unknown count, and one switched off (struck through). */
export const Structured: Story = { render: () => <Applied /> };

/** Structured chips at 375 px: the row wraps. */
export const StructuredNarrow: Story = { render: () => <Applied />, decorators: [narrow] };

/** No chips applied: the structured row renders nothing to clear. */
export const StructuredNone: Story = { render: () => <Applied initial={[]} /> };
