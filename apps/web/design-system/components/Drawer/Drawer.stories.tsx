import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Button } from '../Button';
import { KeyValue } from '../KeyValue';
import { Drawer, type DrawerProps } from './Drawer';

function Example(props: DrawerProps) {
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
      <Drawer {...props} open={open} onOpenChange={setOpen} />
    </>
  );
}

const meta = {
  title: 'Components/Drawer',
  component: Drawer,
  args: {
    open: true,
    onOpenChange: () => undefined,
    title: 'AAPL · Apple',
    description: 'Last close Fri 2 Oct 2026',
    size: 'sm',
    children: (
      <KeyValue
        items={[
          { label: 'Last close', value: 333.69, format: { kind: 'currency' } },
          { label: 'IV30', value: 0.244, format: { kind: 'percent' } },
          { label: 'HV30', value: 0.212, format: { kind: 'percent' } },
          { label: 'From 52w high', value: -0.034, format: { kind: 'delta', digits: 1 } },
          { label: 'Next earnings', value: '19 sessions' },
        ]}
      />
    ),
    footer: <Button variant="primary">Open in Explore</Button>,
  },
  render: (args) => <Example {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a drawer is a container; its content shows its own loading state',
        Empty: 'a drawer is a container; its content shows its own empty state',
        Error: 'a drawer is a container; its content shows its own error state',
        Dense: 'drawer layout follows the density tokens; `sm` is the narrowest',
      },
    },
  },
} satisfies Meta<typeof Drawer>;

export default meta;
type Story = StoryObj<typeof meta>;

/** From the end side. */
export const Default: Story = {};

/** A larger title, for reading panels (the HelpDrawer uses it). */
export const LargeTitle: Story = { args: { titleSize: 'lg' } };

/** From the start side, without a footer. */
export const Start: Story = { args: { side: 'start', footer: undefined } };
