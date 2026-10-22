import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { narrow } from '../../testing';
import { ShowMore } from './ShowMore';

const meta = {
  title: 'Components/ShowMore',
  component: ShowMore,
  args: { shown: 50, total: 312, onMore: fn() },
  parameters: {
    states: {
      notApplicable: {
        Empty: 'a list with nothing in it has no more to show; the list owns its empty state',
        Dense: 'one line at every density; the density tokens size the button',
      },
    },
  },
} satisfies Meta<typeof ShowMore>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** The next page is on its way: the button is busy and ignores clicks. */
export const Loading: Story = { args: { status: 'loading' } };

/** The next page failed: the line says so, the button retries. */
export const Error: Story = { args: { status: 'error' } };

/** Every row is shown: a line, no button. */
export const AllShown: Story = { args: { shown: 312 } };

/** The last page is shorter than a full one: the button says how many it adds. */
export const LastPage: Story = { args: { shown: 300, total: 312 } };

/** On a phone: the line and the button wrap. */
export const Narrow: Story = { decorators: [narrow] };
