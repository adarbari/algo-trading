import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { PartJoin } from './PartJoin';

const meta = {
  title: 'Components/PartJoin',
  component: PartJoin,
  args: {
    join: 'and',
    label: 'and',
    words: 'and',
    joinedByLabel: 'joined by',
    readAsLabel: 'read as',
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a connector is text; the cards around it show loading',
        Empty: 'with no join the caller renders no connector',
        Error: 'a connector has no failure state',
        Dense: 'it has no row density of its own',
      },
    },
  },
} satisfies Meta<typeof PartJoin>;

export default meta;
type Story = StoryObj<typeof meta>;

/** and with the trader's own word: the quiet case. */
export const Default: Story = { args: { words: 'but' } };

export const Or: Story = { args: { join: 'or', label: 'or', words: 'or' } };

export const AndNot: Story = { args: { join: 'and_not', label: 'but not', words: 'except' } };

/** No word of the trader's own: the label alone. */
export const NoWords: Story = { args: { words: undefined } };

export const LongWords: Story = {
  args: {
    join: 'and_not',
    label: 'but not',
    words: 'but not including anything that happens to be',
  },
};

export const Narrow: Story = {
  decorators: [narrow],
  args: {
    join: 'and_not',
    label: 'but not',
    words: 'but not including anything that happens to be',
  },
};
