import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { StatusBadge } from './StatusBadge';

const meta = {
  title: 'Components/StatusBadge',
  component: StatusBadge,
  args: { tone: 'positive', children: 'QUALIFIED' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a badge shows a known state; while it loads, its row shows the loading state',
        Empty: 'a badge always names a state; no state is no badge (or a neutral "UNKNOWN")',
      },
    },
  },
} satisfies Meta<typeof StatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Tones: Story = {
  render: () => (
    <Stack direction="row" gap={2} wrap>
      <StatusBadge tone="positive">QUALIFIED</StatusBadge>
      <StatusBadge tone="accent">WATCH</StatusBadge>
      <StatusBadge tone="warning">EVENT_RISK</StatusBadge>
      <StatusBadge tone="negative">FAILED</StatusBadge>
      <StatusBadge tone="neutral">DRAFT v3</StatusBadge>
      <StatusBadge tone="info">DELAYED 15m</StatusBadge>
    </Stack>
  ),
};

/** Check results with icons, as in the quality checks table. */
export const CheckResults: Story = {
  render: () => (
    <Stack direction="row" gap={2} wrap>
      <StatusBadge tone="positive" icon="check">
        PASS
      </StatusBadge>
      <StatusBadge tone="warning" icon="alert" title="Stale option chains 12.3% (warn above 20%)">
        WARN
      </StatusBadge>
      <StatusBadge tone="negative" icon="alert">
        FAIL
      </StatusBadge>
    </Stack>
  ),
};

export const Error: Story = { args: { tone: 'negative', icon: 'alert', children: 'FAILED' } };

/** A column of decisions at row density. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      <StatusBadge tone="positive">QUALIFIED</StatusBadge>
      <StatusBadge tone="positive">QUALIFIED</StatusBadge>
      <StatusBadge tone="accent">WATCH</StatusBadge>
      <StatusBadge tone="warning">EVENT_RISK</StatusBadge>
    </Stack>
  ),
};
