import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../Stack';
import { Text } from '../Text';
import { VisuallyHidden } from './VisuallyHidden';

const meta = {
  title: 'Primitives/VisuallyHidden',
  component: VisuallyHidden,
  args: { children: 'Only screen readers announce this' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'nothing is drawn; a loading announcement is the Skeleton / live region',
        Empty: 'VisuallyHidden requires children',
        Error: 'nothing is drawn; errors are ErrorState / Banner',
        Dense: 'nothing is drawn, so density does not apply',
      },
    },
  },
  decorators: [
    (Story) => (
      <Stack direction="row" gap={1}>
        <Text tone="down" numeric>
          -0.87%
        </Text>
        <Story />
      </Stack>
    ),
  ],
} satisfies Meta<typeof VisuallyHidden>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Shows only the visible sibling: the hidden text ("down") is for screen readers. */
export const Default: Story = { args: { children: 'down' } };
