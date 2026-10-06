import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { LinkedText, splitTerms, type LinkedTerm } from './LinkedText';

const SENTENCE =
  'The Sahm rule signals a recession when the three-month average unemployment rate rises half a point above its low of the past year.';
const SAHM: LinkedTerm = {
  text: 'Sahm rule',
  href: 'https://fred.stlouisfed.org/series/SAHMREALTIME',
};

const meta = {
  title: 'Components/LinkedText',
  component: LinkedText,
  args: { parts: splitTerms(SENTENCE, [SAHM]).parts },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a sentence is rendered as given; the page around it shows the loading state',
        Empty: 'no link parts renders the plain sentence (the "No links" story)',
        Error: 'a sentence holds no data of its own; the page around it shows a failed load',
      },
    },
  },
} satisfies Meta<typeof LinkedText>;

export default meta;
type Story = StoryObj<typeof meta>;

/** One part is a link: the external mark and the accent colour; the rest is plain text. */
export const Default: Story = {};

/** Several links, each with its hover title. */
export const SeveralLinks: Story = {
  args: {
    parts: splitTerms(SENTENCE, [
      {
        text: 'unemployment rate',
        href: 'https://fred.stlouisfed.org/series/UNRATE',
        title: 'FRED, monthly',
      },
      SAHM,
      { text: 'recession', href: 'https://www.nber.org/research/business-cycle-dating' },
    ]).parts,
  },
};

/** No links: just the sentence, in the chosen tone and size. */
export const NoLinks: Story = {
  args: { parts: [{ text: SENTENCE }], tone: 'secondary', size: 'sm' },
};

/** A list of one-line sentences at the small size, as under a row of meters. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      {[
        'The yield curve inverts when short rates pass long ones.',
        'Financial conditions tighten when credit spreads widen.',
        'Jobless claims rise before the unemployment rate does.',
      ].map((sentence, index) => (
        <LinkedText
          key={sentence}
          size="sm"
          tone="secondary"
          parts={
            splitTerms(sentence, [
              {
                text: ['yield curve', 'credit spreads', 'Jobless claims'][index] ?? '',
                href: 'https://fred.stlouisfed.org/',
              },
            ]).parts
          }
        />
      ))}
    </Stack>
  ),
};

/** Long text wraps like any paragraph; links wrap with it. */
export const LongText: Story = {
  args: { parts: splitTerms(`${SENTENCE} ${SENTENCE}`, [SAHM]).parts },
  decorators: [
    (Story) => (
      <div style={{ maxWidth: '36ch' }}>
        <Story />
      </div>
    ),
  ],
};
