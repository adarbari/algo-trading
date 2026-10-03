import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';

import { Stack } from '../../primitives/Stack';
import { Button } from '../Button';
import { Toast } from './Toast';
import { ToastProvider, useToast } from './ToastProvider';

const meta = {
  title: 'Components/Toast',
  component: Toast,
  args: { tone: 'positive', title: 'Screener saved', description: 'VRP scanner · version 4' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a toast reports a finished action; work in progress shows on its control',
        Empty: 'a toast always has a message',
      },
    },
  },
} satisfies Meta<typeof Toast>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** With a follow-up action and the dismiss button. */
export const WithAction: Story = {
  args: {
    tone: 'info',
    title: 'Criterion removed',
    description: undefined,
    action: { label: 'Undo', onClick: () => undefined },
    onDismiss: () => undefined,
  },
};

export const Error: Story = {
  args: {
    tone: 'negative',
    title: 'Export failed',
    description: 'The file could not be written. Try again.',
    onDismiss: () => undefined,
  },
};

function SaveButton() {
  const toast = useToast();
  return (
    <Button
      variant="primary"
      onClick={() => {
        toast.show({ tone: 'positive', title: 'Screener saved', duration: 0 });
      }}
    >
      Save
    </Button>
  );
}

/** The provider and `useToast()`: Save shows a toast in the corner. */
export const FromProvider: Story = {
  render: () => (
    <ToastProvider>
      <SaveButton />
    </ToastProvider>
  ),
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: 'Save' }));
    await expect(within(canvasElement).getByRole('status')).toHaveTextContent('Screener saved');
  },
};

/** Every tone, stacked. */
export const Dense: Story = {
  render: () => (
    <Stack gap={2}>
      <Toast tone="info" title="Run queued" onDismiss={() => undefined} />
      <Toast tone="positive" title="Screener saved" onDismiss={() => undefined} />
      <Toast tone="warning" title="12.3% of chains are stale" onDismiss={() => undefined} />
      <Toast tone="negative" title="Export failed" onDismiss={() => undefined} />
    </Stack>
  ),
};
