import type { Meta, StoryObj } from '@storybook/react-vite';

import { ErrorState } from './ErrorState';

const meta = {
  title: 'Components/ErrorState',
  component: ErrorState,
  args: {
    title: 'The preview could not run.',
    message: 'The screener service did not answer. Your criteria are saved.',
    onRetry: () => undefined,
  },
  parameters: {
    states: {
      notApplicable: {
        Empty: 'ErrorState is the error state; an empty result is EmptyState',
        Error: 'ErrorState is the error state itself: see Default',
      },
    },
  },
} satisfies Meta<typeof ErrorState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** With a technical detail line. */
export const WithDetail: Story = { args: { detail: 'HTTP 503 · run 2026-10-02T21:04Z' } };

/** The retry in flight. */
export const Loading: Story = { args: { retrying: true } };

/** Compact, without a retry: inside a table or a small panel. */
export const Dense: Story = {
  render: () => <ErrorState compact title="Could not load runs." />,
};
