import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { TaggedSentence, type SentenceSegment } from './TaggedSentence';

const sentence: SentenceSegment[] = [
  { text: 'liquid', kind: 'ask', label: 'needs your call' },
  { text: 'optionable stocks', kind: 'applied', label: 'applied' },
  { text: 'over $5', kind: 'applied', label: 'applied' },
  { text: 'within 5% of their 52-week high', kind: 'formula', label: 'formula' },
  { text: 'that held within support lines for two years', kind: 'gap', label: 'not available yet' },
];

const meta = {
  title: 'Components/TaggedSentence',
  component: TaggedSentence,
  args: { segments: sentence, 'aria-label': 'What was understood' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the sentence is the trader’s own text; the review panel owns the waiting phase',
        Empty: 'a draft always has a sentence',
        Error: 'a failed draft shows the panel’s error state, not a sentence',
        Dense: 'it is prose; there is no row density',
      },
    },
  },
} satisfies Meta<typeof TaggedSentence>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The Describe it example: one span of each kind that matters. */
export const Default: Story = {};

/** Every kind, with plain words between. */
export const Kinds: Story = {
  args: {
    segments: [
      { text: 'Show', kind: 'plain' },
      { text: 'price over $5', kind: 'applied', label: 'applied' },
      { text: 'and', kind: 'plain' },
      { text: 'near the high', kind: 'formula', label: 'formula' },
      { text: 'and', kind: 'plain' },
      { text: 'liquid', kind: 'ask', label: 'needs your call' },
      { text: 'with support', kind: 'gap', label: 'not available yet' },
    ],
  },
};

/** A phone: the sentence wraps like prose and each label stays beside its words. */
export const Narrow: Story = { decorators: [narrow] };
