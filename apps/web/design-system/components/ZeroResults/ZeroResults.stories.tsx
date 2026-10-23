import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { ZeroResults } from './ZeroResults';

const meta = {
  title: 'Components/ZeroResults',
  component: ZeroResults,
  args: {
    title: 'No ideas match all 3 filters',
    items: [
      { id: 'dte', label: 'Switch off DTE', gives: 14 },
      { id: 'liq', label: 'Switch off Liquidity', gives: 9 },
      { id: 'decision', label: 'Switch off Decision', gives: 3 },
    ],
    onPick: () => undefined,
    onClearAll: () => undefined,
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'shown once the filtered result has loaded; loading is Skeleton',
        Empty: 'ZeroResults is the empty result itself: see Default',
        Error: 'a failure is ErrorState, not an empty result',
        Dense: 'one density: the chips follow the density tokens',
      },
    },
  },
} satisfies Meta<typeof ZeroResults>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** No single filter would bring rows back: only Clear all. */
export const NoRecovery: Story = { args: { items: [] } };

/** A phone (375 px): the chips wrap. */
export const Narrow: Story = { decorators: [narrow] };
