import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Button } from '../Button';
import { Banner } from './Banner';

const meta = {
  title: 'Components/Banner',
  component: Banner,
  args: {
    title: 'Sample data',
    children: 'Quotes on this page are delayed 15 minutes (Cboe delayed feed).',
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a banner reports a known condition; loading is Skeleton',
        Empty: 'a banner always has a message',
      },
    },
  },
} satisfies Meta<typeof Banner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** The stale-data notice. */
export const Stale: Story = {
  args: {
    title: undefined,
    asOf: '2026-10-01',
    children: 'Tonight’s run has not finished; screens use yesterday’s features.',
    actions: (
      <Button size="sm" variant="ghost">
        View run
      </Button>
    ),
  },
};

export const Warning: Story = {
  args: {
    tone: 'warning',
    title: 'Partial run',
    children: '515 option chains are stale (12.3%): IV-based columns may lag a day.',
    onDismiss: () => undefined,
  },
};

export const Error: Story = {
  args: {
    tone: 'negative',
    title: 'Nightly run failed',
    children: 'Chains could not be fetched. Screens show Thursday’s data.',
    actions: <Button size="sm">Retry</Button>,
  },
};

/** Stacked banners in a narrow panel. */
export const Dense: Story = {
  render: () => (
    <Stack gap={2}>
      <Banner asOf="2026-10-01" />
      <Banner tone="negative" title="Fetch errors: 3" onDismiss={() => undefined} />
    </Stack>
  ),
};
