import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Field } from '../Field';
import { Icon } from '../Icon';
import { Input } from './Input';

const meta = {
  title: 'Components/Input',
  component: Input,
  args: { 'aria-label': 'Screener name', defaultValue: 'VRP scanner' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a text box holds what the user types; loading belongs to the form or Combobox',
      },
    },
  },
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = {
  args: { defaultValue: undefined, placeholder: 'Name this screener' },
};

export const WithAdornments: Story = {
  render: () => (
    <Stack gap={2}>
      <Input aria-label="Formula" mono defaultValue="iv30 - hv30" start={<Icon name="info" />} />
      <Input aria-label="Price floor" defaultValue="5" align="end" start="$" width="auto" />
      <Input aria-label="Ticker" placeholder="Ticker" sunken />
    </Stack>
  ),
};

export const Error: Story = {
  render: () => (
    <Field label="Screener name" error="A screener with this name already exists" required>
      <Input defaultValue="VRP scanner" />
    </Field>
  ),
};

export const Disabled: Story = { args: { disabled: true } };

/** The small size, as in criteria rows. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      <Input size="sm" aria-label="Threshold 1" defaultValue="50%" align="end" />
      <Input size="sm" aria-label="Threshold 2" defaultValue="10" align="end" />
      <Input size="sm" aria-label="Threshold 3" defaultValue="1.25" align="end" />
    </Stack>
  ),
};
