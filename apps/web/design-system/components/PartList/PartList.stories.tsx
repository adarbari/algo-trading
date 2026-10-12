import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { PartCard } from '../PartCard';
import { PartList } from './PartList';

const meta = {
  title: 'Components/PartList',
  component: PartList,
  args: {
    'aria-label': 'Parts of your sentence',
    children: [
      <PartCard
        key="a"
        kind="applied"
        kindLabel="applied"
        words="optionable stocks"
        readingLabel="We read this as"
        reading="Stocks with listed options."
      />,
      <PartCard
        key="b"
        kind="not-understood"
        kindLabel="not understood"
        words="that feel strong"
      />,
      <PartCard
        key="c"
        kind="kept"
        kindLabel="kept from your screen"
        title="Kept from your screen"
        readingLabel="We read this as"
        reading="Price above 5."
      />,
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'each PartCard has its own redrafting state; the list only orders cards',
        Empty: 'a draft always has at least one part',
        Error: 'each PartCard has its own error state',
        Dense: 'spacing is a fixed token gap',
      },
    },
  },
} satisfies Meta<typeof PartList>;

export default meta;
type Story = StoryObj<typeof meta>;

/** An applied part, a not-understood card and a kept card in order. */
export const Default: Story = {};

export const Narrow: Story = { decorators: [narrow] };
