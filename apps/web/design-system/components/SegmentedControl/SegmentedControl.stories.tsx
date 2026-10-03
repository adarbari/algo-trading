import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { SegmentedControl } from './SegmentedControl';

const RANGE = [
  { value: '3M', label: '3M' },
  { value: '1Y', label: '1Y' },
  { value: '2Y', label: '2Y' },
];

const meta = {
  title: 'Components/SegmentedControl',
  component: SegmentedControl,
  args: { options: RANGE, defaultValue: '1Y', 'aria-label': 'Range' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the options are static labels known up front; nothing loads',
        Empty: 'a segmented control always has two or more options',
      },
    },
  },
} satisfies Meta<typeof SegmentedControl>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Examples: Story = {
  render: () => (
    <Stack gap={3}>
      <SegmentedControl
        aria-label="Criterion mode"
        options={[
          { value: 'hard', label: 'Hard', description: 'must pass' },
          { value: 'soft', label: 'Soft', description: 'scored; a miss is WATCH' },
        ]}
      />
      <SegmentedControl
        aria-label="Option view"
        defaultValue="pro"
        options={[
          { value: 'simple', label: 'Simple' },
          { value: 'pro', label: 'Pro' },
        ]}
      />
      <SegmentedControl aria-label="Range" options={RANGE} defaultValue="2Y" />
    </Stack>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Stack gap={3}>
      <SegmentedControl aria-label="Range" options={RANGE} defaultValue="1Y" disabled />
      <SegmentedControl
        aria-label="Range"
        options={[...RANGE, { value: '5Y', label: '5Y', disabled: true }]}
        defaultValue="3M"
      />
    </Stack>
  ),
};

export const Error: Story = {
  render: () => (
    <Stack gap={1}>
      <SegmentedControl aria-label="Range" options={RANGE} defaultValue="2Y" />
      <Text size="sm" tone="negative">
        Only 1Y of history is stored for this ticker.
      </Text>
    </Stack>
  ),
};

/** The small size, one per criterion row. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      {['hard', 'hard', 'soft'].map((mode, i) => (
        <SegmentedControl
          key={i}
          size="sm"
          aria-label={`Criterion ${i + 1} mode`}
          defaultValue={mode}
          options={[
            { value: 'hard', label: 'Hard' },
            { value: 'soft', label: 'Soft' },
          ]}
        />
      ))}
    </Stack>
  ),
};
