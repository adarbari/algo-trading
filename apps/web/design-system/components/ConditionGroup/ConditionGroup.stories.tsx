import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Button } from '../Button';
import { InfoButton } from '../InfoButton';
import { PartCard } from '../PartCard';
import { ConditionGroup } from './ConditionGroup';

const member = (key: string, words: string, reading: string) => (
  <PartCard
    key={key}
    kind="applied"
    kindLabel="applied"
    words={words}
    readingLabel="We read this as"
    reading={reading}
    redraftingLabel="Redrafting this part"
  />
);

const meta = {
  title: 'Components/ConditionGroup',
  component: ConditionGroup,
  args: {
    kind: 'all',
    kindLabel: 'All of',
    title: 'Liquid and trending',
    connectorLabel: 'and',
    joinedByLabel: 'joined by',
    children: [
      member('a', 'optionable stocks', 'Stocks with listed options.'),
      member('b', 'over $5', 'Price above 5.'),
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the members load themselves; the group only lays them out',
        Empty: 'a group always has members; the Builder removes an empty one',
        Error: 'a group has no failure state of its own',
        Dense: 'spacing is a fixed token gap',
      },
    },
  },
} satisfies Meta<typeof ConditionGroup>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Any: Story = {
  args: { kind: 'any', kindLabel: 'Any of', title: 'Either setup', connectorLabel: 'or' },
};

export const None: Story = {
  args: { kind: 'none', kindLabel: 'None of', title: 'Exclude', connectorLabel: 'and not' },
};

export const WithActions: Story = {
  args: {
    info: <InfoButton label="About this group" onClick={() => undefined} />,
    actions: (
      <>
        <Button size="sm">Either this or the previous</Button>
        <Button size="sm">Ungroup</Button>
      </>
    ),
  },
};

/** A deeper group the Builder cannot edit: one row, members on expanding. */
export const ReadOnly: Story = {
  args: {
    readOnly: true,
    kind: 'any',
    kindLabel: 'Any of',
    connectorLabel: 'or',
    title: 'Group',
    expression: 'price above 5 or volume above 1M',
  },
};

/** The Guide button sits beside the row, outside its toggle button. */
export const ReadOnlyWithInfo: Story = {
  args: {
    ...ReadOnly.args,
    info: <InfoButton label="About any of" onClick={() => undefined} />,
  },
};

export const ReadOnlyOpen: Story = { args: { ...ReadOnly.args, defaultOpen: true } };

export const Narrow: Story = { ...WithActions, decorators: [narrow] };

export const ReadOnlyNarrow: Story = { ...ReadOnlyOpen, decorators: [narrow] };

export const ReadOnlyWithInfoNarrow: Story = { ...ReadOnlyWithInfo, decorators: [narrow] };
