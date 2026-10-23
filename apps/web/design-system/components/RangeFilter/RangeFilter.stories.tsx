import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import { RangeFilter, type RangeFilterProps } from './RangeFilter';

/** The filter with the caller's value. */
function Controlled(props: RangeFilterProps) {
  const [value, setValue] = useState(props.value);
  return <RangeFilter {...props} value={value} onChange={setValue} />;
}

const BINS = [
  { start: 0, end: 7, count: 12 },
  { start: 7, end: 14, count: 30 },
  { start: 14, end: 21, count: 18 },
  { start: 21, end: 28, count: 9 },
  { start: 28, end: 35, count: 4 },
];

const meta = {
  title: 'Components/RangeFilter',
  component: RangeFilter,
  args: {
    value: {},
    onChange: () => undefined,
    label: 'DTE',
    unit: 'days',
    bounds: { min: 0, max: 35 },
  },
  render: (args) => <Controlled {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the bins arrive with the candidates; without them the control is Default',
        Error: 'a number out of range is clamped, never an error',
        Dense: 'the control follows the density tokens',
      },
    },
  },
} satisfies Meta<typeof RangeFilter>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Two empty ends, no histogram. */
export const Default: Story = {};

const WITH_BINS = { value: { max: 14 }, bins: BINS, unknownCount: 37 };

/** An open-ended range (max only) with the histogram and the unknown count. */
export const WithBins: Story = { args: WITH_BINS };

/** Both ends set; typing a minimum above the maximum swaps the two. */
export const Bounded: Story = { args: { value: { min: 7, max: 21 }, bins: BINS } };

/** No bins and no unknown rows: the number fields alone. */
export const Empty: Story = { args: { bins: [], unknownCount: 0 } };

/** A phone (375 px). */
export const Narrow: Story = { decorators: [narrow], args: WITH_BINS };
