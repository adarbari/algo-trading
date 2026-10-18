import type { Meta, StoryObj } from '@storybook/react-vite';

import { Grid } from '../../primitives/Grid';
import { narrow } from '../../testing';
import { StatusBadge } from '../StatusBadge';
import { LinkCard } from './LinkCard';

const meta = {
  title: 'Components/LinkCard',
  component: LinkCard,
  args: {
    href: '/guide/edges/slow-to-update',
    kicker: 'Who is slow to update?',
    title: 'Slow to update',
    description: 'Investors take weeks to absorb news that is already public.',
    exampleLabel: 'e.g.',
    example: 'post-earnings drift, momentum',
    footer: (
      <>
        <StatusBadge tone="neutral">13 edges</StatusBadge>
        <StatusBadge tone="info">2 candidates</StatusBadge>
      </>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a tile is a link to a page that exists; a list of them loads as Skeleton rows',
        Empty: 'a tile always has a title; an empty list is an EmptyState around the grid',
        Error: 'a tile holds no data of its own; the list around it shows a failed load',
      },
    },
  },
} satisfies Meta<typeof LinkCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Title only: no kicker, text, example or pills. */
export const Minimal: Story = {
  args: {
    kicker: undefined,
    description: undefined,
    example: undefined,
    exampleLabel: undefined,
    footer: undefined,
  },
};

/** A grid of tiles of different lengths: footers line up at the bottom. */
export const Dense: Story = {
  render: (args) => (
    <Grid columns={3} gap={3} collapse="md">
      <LinkCard {...args} />
      <LinkCard {...args} title="Forced buyers and sellers" description="Short." />
      <LinkCard
        {...args}
        title="Paid to carry a risk"
        description="Some risks are avoided by most investors, so holding them earns a premium that is rarely competed away, and the text here runs longer."
      />
    </Grid>
  ),
};

/** A phone-width container: one column. */
export const Narrow: Story = { ...Dense, decorators: [narrow] };
