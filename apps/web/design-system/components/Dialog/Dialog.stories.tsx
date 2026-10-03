import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Field } from '../Field';
import { Input } from '../Input';
import { Dialog, type DialogProps } from './Dialog';

/** Opens on load (for the screenshot); the button reopens it. */
function Example(props: DialogProps) {
  const [open, setOpen] = useState(props.open);
  return (
    <>
      <Button
        onClick={() => {
          setOpen(true);
        }}
      >
        Open
      </Button>
      <Dialog {...props} open={open} onOpenChange={setOpen} />
    </>
  );
}

const meta = {
  title: 'Components/Dialog',
  component: Dialog,
  args: {
    open: true,
    onOpenChange: () => undefined,
    title: 'Save screener as',
    description: 'A copy with your criteria and columns.',
    children: (
      <Field label="Name">
        <Input defaultValue="VRP scanner (copy)" />
      </Field>
    ),
    footer: (
      <>
        <Button variant="ghost">Cancel</Button>
        <Button variant="primary">Save</Button>
      </>
    ),
  },
  render: (args) => <Example {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a dialog is a container; its content or its primary Button shows loading',
        Empty: 'a dialog is a container; its content shows its own empty state',
        Error: 'a dialog is a container; its content shows errors (Field error, ErrorState)',
        Dense: 'dialog layout follows the density tokens; Confirm is the smallest size',
      },
    },
  },
} satisfies Meta<typeof Dialog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** A small confirmation that must be answered (no Escape / backdrop close). */
export const Confirm: Story = {
  args: {
    size: 'sm',
    dismissible: false,
    title: 'Delete screener?',
    description: undefined,
    children: <Text tone="secondary">VRP scanner and its 41 saved runs will be deleted.</Text>,
    footer: (
      <>
        <Button variant="ghost">Cancel</Button>
        <Button variant="primary">Delete</Button>
      </>
    ),
  },
};
