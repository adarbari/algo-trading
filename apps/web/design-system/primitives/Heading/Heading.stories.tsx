import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../Stack';
import { Heading } from './Heading';

const meta = {
  title: 'Primitives/Heading',
  component: Heading,
  args: { level: 1, children: 'VRP scanner' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a heading names a section and is known before its data loads',
        Empty: 'an empty heading is an accessibility error; sections always have a name',
        Error: 'errors are shown by ErrorState / Banner, never by the heading',
      },
    },
  },
} satisfies Meta<typeof Heading>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Levels: Story = {
  render: () => (
    <Stack gap={2}>
      <Heading level={1}>h1 18 · page title</Heading>
      <Heading level={2}>h2 13 · panel heading</Heading>
      <Heading level={3}>h3 13 · sub-section</Heading>
      <Heading level={4}>h4 12 · group label</Heading>
    </Stack>
  ),
};

export const Muted: Story = { args: { level: 2, tone: 'muted', children: 'By fetch priority' } };

export const Dense: Story = { args: { level: 2, size: 'sm', children: 'Legs' } };

export const Truncated: Story = {
  args: {
    level: 2,
    truncate: true,
    children: 'Option chains · Fri 2 Oct · 4,203 underlyings expected '.repeat(3),
  },
};
