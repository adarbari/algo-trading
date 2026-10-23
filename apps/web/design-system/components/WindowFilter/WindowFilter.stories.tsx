import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import { WindowFilter, type WindowFilterProps } from './WindowFilter';

/** The filter with the caller's value. */
function Controlled(props: WindowFilterProps) {
  const [value, setValue] = useState(props.value);
  return <WindowFilter {...props} value={value} onChange={setValue} />;
}

const meta = {
  title: 'Components/WindowFilter',
  component: WindowFilter,
  args: {
    value: { amount: 5, unit: 'days' },
    onChange: () => undefined,
    label: 'Within',
    unitLabel: 'Unit',
    units: [
      { value: 'days', label: 'Days' },
      { value: 'sessions', label: 'Sessions' },
    ],
  },
  render: (args) => <Controlled {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the control holds no loaded data',
        Empty: 'an empty number is the Default-off state: see NotSet',
        Error: 'a number out of range is clamped, never an error',
        Dense: 'the control follows the density tokens',
      },
    },
  },
} satisfies Meta<typeof WindowFilter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Sessions chosen. */
export const Sessions: Story = { args: { value: { amount: 3, unit: 'sessions' } } };

/** No number: the filter is off. */
export const NotSet: Story = { args: { value: { amount: null, unit: 'days' } } };

/** A phone (375 px): the unit toggle wraps under the number if it must. */
export const Narrow: Story = { decorators: [narrow] };
