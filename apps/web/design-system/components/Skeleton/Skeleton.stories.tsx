import type { Meta, StoryObj } from '@storybook/react-vite';

import { Skeleton } from './Skeleton';

const meta = {
  title: 'Components/Skeleton',
  component: Skeleton,
  args: { label: 'Loading ideas…' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'Skeleton is the loading state itself: every story shows it',
        Empty: 'Skeleton stands in for content still loading; empty content is EmptyState',
        Error: 'Skeleton stands in for content still loading; a failure is ErrorState',
      },
    },
  },
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Lines of text; the last one shorter. */
export const Default: Story = {};

/** A chart-sized block. */
export const Rect: Story = { args: { variant: 'rect', label: 'Loading chart…' } };

/** Table rows at the density's row height. */
export const Table: Story = { args: { variant: 'table', rows: 6, columns: 5 } };

/** One line and a short table: inside a small panel. */
export const Dense: Story = { args: { variant: 'table', rows: 3, columns: 3 } };
