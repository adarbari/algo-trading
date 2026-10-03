import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { ShareBar } from './ShareBar';

const meta = {
  title: 'Components/ShareBar',
  component: ShareBar,
  args: { value: 0.941, label: 'Liquid names coverage' },
  parameters: {
    states: {
      notApplicable: {
        Error: 'a share bar draws a number it is given; the panel around it shows a failed load',
      },
    },
  },
} satisfies Meta<typeof ShareBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithLabel: Story = {
  args: { showLabel: true, size: 'md', value: 0.862, label: 'Option chains OK' },
};

/** Status tones for pass / warn / fail shares. */
export const Tones: Story = {
  render: () => (
    <Stack gap={2}>
      <ShareBar value={1} label="Priority ETFs" tone="positive" />
      <ShareBar value={0.123} label="Stale chains" tone="warning" />
      <ShareBar value={0.015} label="No chain" tone="muted" />
      <ShareBar value={0.004} label="Fetch errors" tone="negative" />
    </Stack>
  ),
};

export const Loading: Story = { args: { loading: true } };

/** Unknown share: empty track and an em dash. */
export const Empty: Story = { args: { value: null } };

export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      {[1, 0.996, 0.941, 0.76].map((value) => (
        <ShareBar key={value} value={value} label={`Tier at ${value}`} />
      ))}
    </Stack>
  ),
};
