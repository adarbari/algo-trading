import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { TrackRecordChip } from './TrackRecordChip';

const meta = {
  title: 'Components/TrackRecordChip',
  component: TrackRecordChip,
  args: { status: 'evidenced' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a chip is a label from a stored status; the list around it shows loading',
        Error: 'a chip holds no data of its own; the list around it shows a failed load',
        Narrow: 'a chip is one short label with no container or pointer rule',
      },
    },
  },
} satisfies Meta<typeof TrackRecordChip>;

export default meta;
type Story = StoryObj<typeof meta>;

/** An edge passed the frozen period. */
export const Default: Story = {};

export const Candidate: Story = { args: { status: 'candidate', sessions: 42 } };

/** Not run yet: the empty state of a track record. */
export const Empty: Story = { args: { status: 'not-run' } };

/** An exploratory record never feeds the chip: nothing is rendered. */
export const Exploratory: Story = { args: { exploratory: true } };

/** Beside screener names in a list. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      <TrackRecordChip status="evidenced" />
      <TrackRecordChip status="candidate" sessions={42} />
      <TrackRecordChip status="candidate" sessions={1} />
      <TrackRecordChip status="not-run" />
    </Stack>
  ),
};
