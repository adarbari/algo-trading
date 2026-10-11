import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Stack } from '../../primitives/Stack';
import { EvidenceMeter } from './EvidenceMeter';

const MILESTONES = [
  { at: 10, label: 'first read' },
  { at: 25, label: 'checkpoint' },
  { at: 40, label: 'decision' },
];

const meta = {
  title: 'Components/EvidenceMeter',
  component: EvidenceMeter,
  args: {
    label: 'Closed paper trades',
    value: 18,
    max: 40,
    milestones: MILESTONES,
    caption: 'On pace for 12 Nov.',
  },
  parameters: {
    states: {
      notApplicable: {
        Error: 'a meter draws the numbers it is given; the panel around it shows a failed load',
        Loading: 'the page shows its own skeleton until the counts exist',
      },
    },
  },
} satisfies Meta<typeof EvidenceMeter>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 18 of 40: the first milestone reached, the next two still ahead. */
export const Default: Story = {};

/** Nothing collected yet (a real zero, drawn as an empty filled-to-0 track, not as unknown). */
export const Zero: Story = { args: { value: 0, caption: 'No trades closed yet.' } };

/** All milestones reached: the fill runs to the end. */
export const Complete: Story = { args: { value: 40, caption: 'Enough evidence to decide.' } };

/** A value past the need: the fill clamps to the end; the reading still says what was collected. */
export const OverMax: Story = { args: { value: 52 } };

/** Unknown: a dashed empty track and the reason, never a zero. */
export const Empty: Story = {
  args: { state: 'unknown', unknownLabel: 'No trades recorded yet', caption: undefined },
};

/** No milestones and no caption: label, reading, track. */
export const Plain: Story = { args: { milestones: [], caption: undefined } };

export const Dense: Story = {
  render: (args) => (
    <Stack gap={2}>
      <EvidenceMeter {...args} label="Paper trades" value={18} />
      <EvidenceMeter
        {...args}
        label="Sessions"
        value={9}
        max={20}
        milestones={[]}
        caption={undefined}
      />
      <EvidenceMeter
        {...args}
        label="Independent windows"
        value={1}
        max={4}
        milestones={[]}
        caption={undefined}
      />
    </Stack>
  ),
};

/** A phone-width container: ticks and their names stay inside the track's ends. */
export const Narrow: Story = { decorators: [narrow] };
