import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Kbd } from './Kbd';

const meta = {
  title: 'Components/Kbd',
  component: Kbd,
  args: { keys: ['/'] },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'Kbd is static text; it never loads',
        Empty: 'Kbd always shows at least one key',
        Error: 'Kbd is static text; it cannot fail',
      },
    },
  },
} satisfies Meta<typeof Kbd>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** A chord: keys pressed together. */
export const Chord: Story = { args: { keys: ['Ctrl', 'K'] } };

/** In a hint line, at caption size. */
export const Dense: Story = {
  render: () => (
    <Stack direction="row" gap={1} align="center" wrap>
      <Text size="sm" tone="muted">
        Press
      </Text>
      <Kbd keys={['/']} size="xs" />
      <Text size="sm" tone="muted">
        to search,
      </Text>
      <Kbd keys={['Shift', 'Click']} size="xs" />
      <Text size="sm" tone="muted">
        to select a range,
      </Text>
      <Kbd keys={['Esc']} size="xs" />
      <Text size="sm" tone="muted">
        to close.
      </Text>
    </Stack>
  ),
};
