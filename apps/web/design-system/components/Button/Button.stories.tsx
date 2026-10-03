import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Button } from './Button';

const meta = {
  title: 'Components/Button',
  component: Button,
  args: { children: 'Save draft' },
  parameters: {
    states: {
      notApplicable: {
        Empty: 'a button always has a label; an icon-only action is IconButton',
      },
    },
  },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** The four variants, as the screener header and criteria panel use them. */
export const Variants: Story = {
  render: () => (
    <Stack direction="row" gap={2} wrap>
      <Button variant="primary">Finalize v3</Button>
      <Button>Save draft</Button>
      <Button variant="ghost">Discard</Button>
      <Button variant="dashed" icon="plus">
        Add criterion
      </Button>
    </Stack>
  ),
};

export const WithIcons: Story = {
  render: () => (
    <Stack direction="row" gap={2} wrap>
      <Button icon="refresh">Re-run chains</Button>
      <Button iconEnd="external">Open run record</Button>
      <Button icon="columns" variant="ghost">
        Columns
      </Button>
      <Button iconEnd="chevron-down">Export</Button>
    </Stack>
  ),
};

export const Loading: Story = {
  render: () => (
    <Stack direction="row" gap={2} wrap>
      <Button variant="primary" loading>
        Finalizing
      </Button>
      <Button loading>Saving</Button>
    </Stack>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Stack direction="row" gap={2} wrap>
      <Button variant="primary" disabled>
        Finalize v3
      </Button>
      <Button disabled>Save draft</Button>
      <Button variant="ghost" disabled>
        Discard
      </Button>
    </Stack>
  ),
};

export const Error: Story = {
  render: () => (
    <Stack direction="row" gap={2} align="center" wrap>
      <Text tone="negative">Save failed: the draft changed on the server.</Text>
      <Button icon="refresh">Try again</Button>
    </Stack>
  ),
};

/** Small buttons, as in a panel header or chip row. */
export const Dense: Story = {
  render: () => (
    <Stack direction="row" gap={1.5} wrap>
      <Button size="sm">Compare selected</Button>
      <Button size="sm" variant="ghost" icon="filter">
        Filter
      </Button>
      <Button size="sm" variant="dashed" icon="plus">
        Dimension
      </Button>
      <Button size="sm" variant="primary">
        Run
      </Button>
    </Stack>
  ),
};

export const FullWidth: Story = { args: { fullWidth: true, variant: 'primary' } };
