import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { PartCard } from '../PartCard';
import { PartJoin } from '../PartJoin';
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
        redraftingLabel="Redrafting this part"
      />,
      <PartCard
        key="b"
        kind="not_understood"
        kindLabel="not understood"
        words="that feel strong"
        redraftingLabel="Redrafting this part"
      />,
      <PartCard
        key="c"
        kind="applied"
        kindLabel="applied"
        origin="kept"
        keptLabel="kept from your screen"
        title="Kept from your screen"
        readingLabel="We read this as"
        reading="Price above 5."
        redraftingLabel="Redrafting this part"
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

/** An applied part, a not_understood card and a kept card in order. */
export const Default: Story = {};

export const Narrow: Story = { decorators: [narrow] };

const joinedCards = (join: 'and' | 'or' | 'and_not', label: string, words: string) => [
  <PartCard
    key="a"
    kind="applied"
    kindLabel="applied"
    words="optionable stocks"
    reading="Stocks with listed options."
    readingLabel="We read this as"
    redraftingLabel="Redrafting this part"
  />,
  <PartJoin
    key="j"
    join={join}
    label={label}
    words={words}
    joinedByLabel="joined by"
    readAsLabel="read as"
  />,
  <PartCard
    key="b"
    kind="applied"
    kindLabel="applied"
    words="over $5"
    reading="Price above 5."
    readingLabel="We read this as"
    redraftingLabel="Redrafting this part"
  />,
];

/** A connector between parts: and, or and but not, then no connector at all. */
export const Joined: Story = {
  render: (args) => (
    <>
      <PartList {...args}>{joinedCards('and', 'and', 'but')}</PartList>
      <PartList {...args}>{joinedCards('or', 'or', 'or')}</PartList>
      <PartList {...args}>{joinedCards('and_not', 'but not', 'except')}</PartList>
    </>
  ),
};

export const JoinedNarrow: Story = { ...Joined, decorators: [narrow] };
