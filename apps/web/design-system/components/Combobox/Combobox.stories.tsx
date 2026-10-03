import type { Meta, StoryObj } from '@storybook/react-vite';
import { useRef, useState } from 'react';
import { userEvent, within } from 'storybook/test';

import { Field } from '../Field';
import { Combobox, type ComboboxOption } from './Combobox';

const FEATURES: ComboboxOption[] = [
  {
    value: 'iv30@v1.iv30',
    label: 'iv30@v1.iv30',
    description: 'Our 30-day ATM implied volatility',
    group: 'Catalogue',
  },
  {
    value: 'price_stats@v1.close',
    label: 'price_stats@v1.close',
    description: 'Last close',
    group: 'Catalogue',
  },
  {
    value: 'price_stats@v1.adv_usd_20d',
    label: 'price_stats@v1.adv_usd_20d',
    description: '20-day average dollar volume',
    group: 'Catalogue',
  },
  {
    value: 'earnings@v1.days_to_earnings',
    label: 'earnings@v1.days_to_earnings',
    description: 'Sessions until next earnings',
    group: 'Catalogue',
  },
  {
    value: 'iv_hv_spread',
    label: 'iv_hv_spread',
    description: 'IV30 − HV30, vol points',
    badge: 'formula',
    group: 'Your formulas',
  },
  {
    value: 'iv_hv_ratio',
    label: 'iv_hv_ratio',
    description: 'IV30 ÷ HV30',
    badge: 'formula',
    group: 'Your formulas',
  },
  {
    value: 'near_52w',
    label: 'near_52w',
    description: 'Within 10% of the 52-week high or low',
    badge: 'formula',
    group: 'Your formulas',
    disabled: true,
  },
];

/** Opens the list, as a user would, so the screenshot shows it. */
const openList: Story['play'] = async ({ canvasElement }) => {
  await userEvent.click(within(canvasElement).getByRole('combobox'));
};

const meta = {
  title: 'Components/Combobox',
  component: Combobox,
  args: {
    options: FEATURES,
    'aria-label': 'Feature',
    placeholder: 'Choose a feature…',
    mono: true,
  },
  parameters: { layout: 'padded' },
} satisfies Meta<typeof Combobox>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { defaultValue: 'iv30@v1.iv30' } };

/** The feature picker open: groups, descriptions, kind badges, the selection checked. */
export const Open: Story = { args: { defaultValue: 'price_stats@v1.close' }, play: openList };

/** Typing filters by label, description and badge. */
export const Filtered: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.type(within(canvasElement).getByRole('combobox'), 'volatility');
  },
};

export const Loading: Story = {
  args: { options: [], loading: true, filter: 'none' },
  play: openList,
};

export const Empty: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.type(within(canvasElement).getByRole('combobox'), 'zzz');
  },
};

export const Error: Story = {
  render: (args) => (
    <Field label="Feature" error="Pick a feature to compare against">
      <Combobox {...args} options={[]} error="The feature catalogue failed to load" />
    </Field>
  ),
  play: openList,
};

/** Small, in a criteria row, labels not in mono. */
export const Dense: Story = {
  args: {
    size: 'sm',
    mono: false,
    defaultValue: 'b',
    options: [
      { value: 'a', label: 'Hard: must pass' },
      { value: 'b', label: 'Soft: scored' },
      { value: 'c', label: 'Flag only' },
    ],
  },
  play: openList,
};

function AsyncPicker() {
  const [options, setOptions] = useState<ComboboxOption[]>(FEATURES);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const search = (query: string) => {
    setLoading(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const q = query.toLowerCase();
      setOptions(FEATURES.filter((f) => `${f.label} ${f.description ?? ''}`.includes(q)));
      setLoading(false);
    }, 300);
  };
  return (
    <Field label="Feature" hint="Searches the catalogue as you type">
      <Combobox
        options={options}
        filter="none"
        loading={loading}
        onInputChange={search}
        mono
        placeholder="Search features…"
      />
    </Field>
  );
}

/** Async options: the caller fetches on input and passes results and `loading`. */
export const Async: Story = { render: () => <AsyncPicker /> };
