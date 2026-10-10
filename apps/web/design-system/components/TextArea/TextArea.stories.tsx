import type { Meta, StoryObj } from '@storybook/react-vite';

import { Field } from '../Field';
import { TextArea } from './TextArea';

const meta = {
  title: 'Components/TextArea',
  component: TextArea,
  args: {
    'aria-label': 'Why it should last',
    defaultValue: 'Investors underreact to news; the effect concentrates when news arrives.',
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a text box holds what the user types; loading belongs to the form around it',
        Dense: 'one density: the box grows with the text',
      },
    },
  },
} satisfies Meta<typeof TextArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = {
  args: { defaultValue: undefined, placeholder: 'Why should it keep working?' },
};

export const Error: Story = {
  render: () => (
    <Field label="Why it should last" error="Say why it should keep working" required>
      <TextArea defaultValue="" />
    </Field>
  ),
};

export const Disabled: Story = { args: { disabled: true } };
