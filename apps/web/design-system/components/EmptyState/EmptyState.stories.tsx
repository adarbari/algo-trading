import type { Meta, StoryObj } from '@storybook/react-vite';

import { Button } from '../Button';
import { EmptyState } from './EmptyState';

const meta = {
  title: 'Components/EmptyState',
  component: EmptyState,
  args: {
    title: 'No ideas for Mon 5 Oct',
    description: 'None of your screeners qualified a name today. Loosen a criterion or add one.',
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'EmptyState is shown once loading has finished; loading is Skeleton',
        Empty: 'EmptyState is the empty state itself: see Default',
        Error: 'a failure is ErrorState, not an empty result',
      },
    },
  },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** With an icon and an action. */
export const WithAction: Story = {
  args: {
    icon: 'search',
    title: 'No tickers match',
    description: 'Clear a filter to see more of the universe.',
    action: <Button size="sm">Clear filters</Button>,
  },
};

/** The dashed placeholder outline (a tab not built yet). */
export const Bordered: Story = {
  args: {
    bordered: true,
    title: 'Events',
    description: 'Earnings, dividends, splits, ticker and index changes, in one timeline.',
  },
};

/** Compact and left-aligned, inside a table or a small panel. */
export const Dense: Story = {
  args: { compact: true, title: 'No runs yet', description: undefined },
};
