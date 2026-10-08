import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { KeyHints } from './KeyHints';

const meta = {
  title: 'Components/KeyHints',
  component: KeyHints,
  args: {
    hints: [
      { keys: ['j', 'k'], label: 'move' },
      { keys: ['c'], label: 'compare' },
      { keys: ['x'], label: 'dismiss' },
      { keys: ['Enter'], label: 'open in Explore' },
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'KeyHints is static text; it never loads',
        Empty: 'a panel with no shortcuts renders no KeyHints',
        Error: 'KeyHints is static text; it cannot fail',
      },
    },
  },
} satisfies Meta<typeof KeyHints>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** One hint, in a toolbar. */
export const Dense: Story = { args: { hints: [{ keys: ['/'], label: 'search' }] } };

/**
 * A phone (375 px): the hints wrap. Under a coarse pointer (the phone itself, not this frame)
 * the row is hidden altogether: a finger has no keys.
 */
export const Narrow: Story = { decorators: [narrow] };
