import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { PhoneFold } from './PhoneFold';

const meta = {
  title: 'Components/PhoneFold',
  component: PhoneFold,
  args: { label: 'Record', children: 'Win rate 58.0% vs 51.0% base · lift +7 pts · 80 trades' },
  parameters: {
    states: {
      notApplicable: {
        Empty: 'it folds what the caller gives it; the caller owns an empty state',
        Loading: 'the caller renders its own loading state inside or instead of it',
        Error: 'the caller renders its own error state inside or instead of it',
        Dense: 'it adds no spacing of its own; the Disclosure takes the density tokens',
      },
    },
  },
} satisfies Meta<typeof PhoneFold>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Wide: the content is shown in place, no summary. */
export const Default: Story = {};

/** A phone (375 px): the content is behind its summary. */
export const Narrow: Story = { decorators: [narrow] };
