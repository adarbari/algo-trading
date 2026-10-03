import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Input } from '../Input';
import { Field } from './Field';

const meta = {
  title: 'Components/Field',
  component: Field,
  args: {
    label: 'Screener name',
    hint: 'Shown on Ideas and in shared results',
    children: <Input defaultValue="VRP scanner" />,
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a field wraps a control; loading is shown by the control (Combobox) or form',
        Empty: 'an empty field is its control with a placeholder: see Input / Empty',
      },
    },
  },
} satisfies Meta<typeof Field>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Required: Story = { args: { required: true } };

export const Error: Story = {
  args: { error: 'A screener with this name already exists', required: true },
};

export const Disabled: Story = { args: { disabled: true } };

/** Label column beside the control, several fields stacked (settings forms). */
export const Dense: Story = {
  render: () => (
    <Stack gap={2}>
      <Field label="Universe" layout="inline">
        <Input mono defaultValue="vrp_universe" />
      </Field>
      <Field label="Min price" layout="inline" hint="Last close, USD">
        <Input defaultValue="5" align="end" start="$" />
      </Field>
      <Field label="Max names" layout="inline" error="At most 500">
        <Input defaultValue="900" align="end" />
      </Field>
    </Stack>
  ),
};

export const HiddenLabel: Story = { args: { hideLabel: true, hint: undefined } };
