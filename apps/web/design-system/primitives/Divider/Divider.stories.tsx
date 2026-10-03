import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../Stack';
import { Text } from '../Text';
import { Divider } from './Divider';

const meta = {
  title: 'Primitives/Divider',
  component: Divider,
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a divider is static decoration between groups',
        Empty: 'a divider has no content',
        Error: 'a divider has no error state',
      },
    },
  },
  decorators: [
    (Story) => (
      <Stack gap={2}>
        <Text>Above</Text>
        <Story />
        <Text>Below</Text>
      </Stack>
    ),
  ],
} satisfies Meta<typeof Divider>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Soft: Story = { args: { tone: 'soft' } };

export const Vertical: Story = {
  decorators: [
    (Story) => (
      <Stack direction="row" gap={3}>
        <Text>Filters</Text>
        <Story />
        <Text>Columns</Text>
      </Stack>
    ),
  ],
  args: { orientation: 'vertical' },
};

export const Dense: Story = { args: { tone: 'soft', decorative: true } };
