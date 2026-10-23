import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import { ExpandLink } from './ExpandLink';

const meta = {
  title: 'Components/ExpandLink',
  component: ExpandLink,
  args: { open: false, onOpenChange: () => undefined, children: 'Win 58% vs 51% base' },
  render: (args) => {
    const [open, setOpen] = useState(args.open);
    return <ExpandLink {...args} open={open} onOpenChange={setOpen} />;
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a link shows the words it is given; the cell around it shows loading',
        Empty: 'a link with no words is not rendered',
        Dense: 'one density: it takes the text size around it',
        Error: 'a link holds no data of its own',
      },
    },
  },
} satisfies Meta<typeof ExpandLink>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Open: Story = { args: { open: true } };

/** A phone (375 px): a long label wraps inside its cell. */
export const Narrow: Story = {
  decorators: [narrow],
  args: { children: 'Win 58% vs 51% base on 120 trades in the frozen period of an edge' },
};
