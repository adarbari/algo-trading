import type { Meta, StoryObj } from '@storybook/react-vite';

import { Heading } from '../Heading';
import { Stack } from '../Stack';
import { Text } from '../Text';
import { Surface } from './Surface';

const meta = {
  title: 'Primitives/Surface',
  component: Surface,
  args: {
    padding: 4,
    children: <Text>A panel surface: 1 px border, 6 px radius, no shadow.</Text>,
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'Surface is a container; loading is the Skeleton / Panel state of its content',
        Error: 'Surface is a container; errors are shown by ErrorState / Banner inside it',
      },
    },
  },
} satisfies Meta<typeof Surface>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Tones: Story = {
  render: () => (
    <Stack gap={3}>
      <Surface tone="surface" padding={3}>
        <Text>surface: panels, top bar</Text>
      </Surface>
      <Surface tone="row" border="none" padding={3}>
        <Text>row: wells, hovered rows</Text>
      </Surface>
      <Surface tone="bg" padding={3}>
        <Text>bg: the canvas</Text>
      </Surface>
      <Surface tone="accent" borderTone="accent" padding={3}>
        <Text>accent: selected</Text>
      </Surface>
    </Stack>
  ),
};

export const Panel: Story = {
  render: () => (
    <Surface as="section" aria-labelledby="panel-title" padding={0} clip>
      <Surface border="bottom" borderTone="soft" radius="none" paddingX={4} paddingY={2.5}>
        <Heading level={2} id="panel-title">
          Completeness · last 10 sessions
        </Heading>
      </Surface>
      <Surface border="none" radius="none" padding={4}>
        <Text tone="muted" size="sm">
          Option chains and IV start on Fri 2 Oct: Cboe has no history.
        </Text>
      </Surface>
    </Surface>
  ),
};

export const Selected: Story = {
  args: { borderTone: 'accent', children: <Text>Drill-down: the selected panel.</Text> },
};

export const Empty: Story = { args: { children: undefined } };

export const Dense: Story = {
  args: { padding: 2, radius: 'md', children: <Text size="md">Dense: 8 px, 4 px radius.</Text> },
};
