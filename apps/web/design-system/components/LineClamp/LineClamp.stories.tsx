import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Text } from '../../primitives/Text';
import { LineClamp } from './LineClamp';

const LONG =
  'A long one-line description that wraps onto more than two lines and is cut off. '.repeat(4);

const meta = {
  title: 'Components/LineClamp',
  component: LineClamp,
  args: {
    children: (
      <Text as="p" size="sm" tone="secondary">
        {LONG}
      </Text>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a clamp wraps text already loaded; loading is Skeleton',
        Empty: 'a clamp exists only around text',
        Error: 'a clamp reports nothing',
        Dense: 'the text inside is sized by Text and the density tokens',
      },
    },
  },
} satisfies Meta<typeof LineClamp>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Short: Story = {
  args: {
    children: (
      <Text as="p" size="sm" tone="secondary">
        Shares closing above their one-month high.
      </Text>
    ),
  },
};

export const Narrow: Story = { decorators: [narrow] };
