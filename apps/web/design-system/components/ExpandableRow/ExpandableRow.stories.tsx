import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { Mono } from '../../primitives/Mono';
import { Text } from '../../primitives/Text';
import { narrow } from '../../testing';
import { StatusBadge } from '../StatusBadge';
import { ExpandableRow } from './ExpandableRow';

const meta = {
  title: 'Components/ExpandableRow',
  component: ExpandableRow,
  args: {
    title: <Mono>vrp_scanner</Mono>,
    badge: <StatusBadge tone="neutral">Preset</StatusBadge>,
    secondary: (
      <Text size="sm" tone="secondary">
        Last run 2026-10-07
      </Text>
    ),
    essential: '12',
    open: false,
    onOpenChange: () => undefined,
    children: <Text size="sm">Criteria, top hits and actions.</Text>,
  },
  render: (args) => {
    const [open, setOpen] = useState(args.open);
    return <ExpandableRow {...args} open={open} onOpenChange={setOpen} />;
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a row shows what it is given; the detail loads itself once open',
        Empty: 'a list with no rows shows its own empty state',
        Dense: 'one density: the rows are as tall as the density tokens make them',
        Error: 'a row holds no data of its own; the list shows a failed load',
      },
    },
  },
} satisfies Meta<typeof ExpandableRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Open: Story = { args: { open: true } };

/** A phone (375 px): the title, badge and hits only. */
export const Narrow: Story = { decorators: [narrow], args: { open: true } };
