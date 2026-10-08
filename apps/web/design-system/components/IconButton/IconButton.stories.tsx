import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { IconButton } from './IconButton';
import { narrow } from '../../testing';

const meta = {
  title: 'Components/IconButton',
  component: IconButton,
  args: { icon: 'close', label: 'Remove criterion' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'an icon-only action shows progress in the region it updates, not on itself',
        Empty: 'an icon button always has an icon and a label',
      },
    },
  },
} satisfies Meta<typeof IconButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Variants: Story = {
  render: () => (
    <Stack direction="row" gap={2} align="center">
      <IconButton icon="close" label="Remove" />
      <IconButton icon="columns" label="Choose columns" variant="secondary" />
      <IconButton icon="refresh" label="Refresh" variant="secondary" />
      <IconButton icon="filter" label="Filter" />
      <IconButton icon="external" label="Open in a new tab" />
    </Stack>
  ),
};

export const Disabled: Story = { args: { disabled: true } };

export const Error: Story = {
  render: () => (
    <Stack direction="row" gap={1} align="center">
      <Text tone="negative">Could not load the chain.</Text>
      <IconButton icon="refresh" label="Retry" variant="secondary" />
    </Stack>
  ),
};

/** Small, as inside a chip or an input. */
export const Dense: Story = {
  render: () => (
    <Stack direction="row" gap={1} align="center">
      <IconButton icon="close" label="Clear" size="sm" />
      <IconButton icon="chevron-down" label="Open" size="sm" />
      <IconButton icon="drag-handle" label="Reorder" size="sm" />
    </Stack>
  ),
};

/** A 375 px phone frame; under a coarse pointer the control floors apply. */
export const Narrow: Story = { ...Dense, decorators: [narrow] };
