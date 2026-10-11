import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { TextBlock } from './TextBlock';

const LONG = Array.from(
  { length: 40 },
  (_, i) => `line ${String(i + 1)} of a long model answer`,
).join('\n');

const meta = {
  title: 'Components/TextBlock',
  component: TextBlock,
  args: {
    label: 'Raw model answer',
    text: 'Sure! Support lines are not in the catalogue, so here is a plain description instead.',
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the text is already in hand; loading is Skeleton',
        Error: 'it shows text, it has no failure of its own',
        Dense: 'one size at every density; the font tokens size it',
      },
    },
  },
} satisfies Meta<typeof TextBlock>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Past the height cap the block scrolls (and takes the keyboard focus to do so). */
export const Long: Story = { args: { text: LONG } };

export const Empty: Story = { args: { text: null, empty: 'The provider returned no text' } };

export const Narrow: Story = {
  args: { text: `${'a_very_long_unbroken_token_'.repeat(8)}\n${LONG}`, size: 'sm' },
  decorators: [narrow],
};
