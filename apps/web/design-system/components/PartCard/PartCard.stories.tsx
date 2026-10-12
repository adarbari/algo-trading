import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { narrow } from '../../testing';
import { Button } from '../Button';
import { SegmentedControl } from '../SegmentedControl';
import { PartList } from '../PartList';
import { PartCard, type PartKind } from './PartCard';

const labels = {
  readingLabel: 'We read this as',
  checkReadingLabel: 'check this reading',
  redraftingLabel: 'Redrafting this part',
  retryLabel: 'Try again',
  editedLabel: 'edited',
};

const rows = (
  <ul style={{ margin: 0, paddingInlineStart: 'var(--space-4)' }}>
    <li>close above 5</li>
    <li>optionable is true</li>
  </ul>
);

const actions = (
  <>
    <SegmentedControl
      aria-label="Pick another reading"
      defaultValue="a"
      options={[
        { value: 'a', label: 'Over $5' },
        { value: 'b', label: 'Over $10' },
      ]}
    />
    <Button size="sm" variant="ghost">
      Retype this part
    </Button>
  </>
);

const meta = {
  title: 'Components/PartCard',
  component: PartCard,
  args: {
    kind: 'applied',
    kindLabel: 'applied',
    words: 'optionable stocks over $5',
    reading: 'Stocks with listed options and a price above $5.',
    readingSource: 'model',
    rows,
    actions,
    ...labels,
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the Redrafting story is the loading state of one card',
        Empty: 'a card always has words or a title',
        Dense: 'the card has no row density of its own; the rows component owns it',
      },
    },
  },
} satisfies Meta<typeof PartCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

const kinds: [PartKind, string][] = [
  ['applied', 'applied'],
  ['formula', 'formula to review'],
  ['ask', 'needs your call'],
  ['gap', 'not available yet'],
  ['not-understood', 'not understood'],
  ['kept', 'kept from your screen'],
];

/** Every kind, in one list. */
export const Kinds: Story = {
  render: (args) => (
    <PartList aria-label="Parts of your sentence">
      {kinds.map(([kind, kindLabel]) => (
        <PartCard
          key={kind}
          {...args}
          kind={kind}
          kindLabel={kindLabel}
          {...(kind === 'kept' ? { words: undefined, title: 'Kept from your screen' } : {})}
          {...(kind === 'not-understood'
            ? { rows: undefined, actions: undefined, reading: undefined }
            : {})}
        />
      ))}
    </PartList>
  ),
};

/** Words the model could not place: the words, no reading. */
export const NotUnderstood: Story = {
  args: {
    kind: 'not-understood',
    kindLabel: 'not understood',
    words: 'that feel strong',
    reading: undefined,
    rows: undefined,
  },
};

/** Criteria tied to no words: no quote, a title instead. */
export const Kept: Story = {
  args: {
    kind: 'kept',
    kindLabel: 'kept from your screen',
    words: undefined,
    title: 'Kept from your screen',
    reading: undefined,
  },
};

/** A reading the model did not write shows the muted note. */
export const CheckThisReading: Story = { args: { readingSource: 'server' } };

export const NoReading: Story = { args: { readingSource: null, reading: undefined } };

/** This card only: the words stay, the body waits. */
export const Redrafting: Story = { args: { state: 'redrafting' } };

export const Error: Story = {
  args: {
    state: 'error',
    errorMessage: 'This part could not be redrafted.',
    onRetry: () => undefined,
  },
};

export const Edited: Story = { args: { edited: true } };

export const Disabled: Story = { args: { state: 'disabled' } };

/** The words become an input with Apply / Cancel. */
export const Retype: Story = {
  render: (args) => {
    const [value, setValue] = useState('optionable stocks over $5');
    return (
      <PartCard
        {...args}
        retype={{
          value,
          onValueChange: setValue,
          onApply: () => undefined,
          onCancel: () => undefined,
          inputLabel: 'Retype this part',
          applyLabel: 'Apply',
          cancelLabel: 'Cancel',
        }}
      />
    );
  },
};

/** A phone: the badge moves above the words and the actions fill the width. */
export const Narrow: Story = { decorators: [narrow] };

export const NarrowRetype: Story = { ...Retype, decorators: [narrow] };
