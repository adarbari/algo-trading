import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { LinkedProse, type LinkedProsePart } from './LinkedProse';

const CAVEAT: LinkedProsePart[] = [
  { text: 'Earnings days run 3 to 10 times normal volume; check ' },
  { text: 'last_earnings_date', href: '/guide/fields/last_earnings_date' },
  { text: ' before reading ' },
  { text: 'rel_volume', href: '/guide/fields/rel_volume' },
  { text: ' as conviction.' },
];

const meta = {
  title: 'Components/LinkedProse',
  component: LinkedProse,
  args: { parts: CAVEAT, monoLinks: true },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a paragraph is rendered as given; the page around it shows the loading state',
        Empty: 'no link parts renders the plain paragraph (the "No links" story)',
        Error: 'a paragraph holds no data of its own; the page around it shows a failed load',
      },
    },
  },
} satisfies Meta<typeof LinkedProse>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Catalogue names are links to their pages, in the mono face; the rest is plain text. */
export const Default: Story = {};

/** The links take the paragraph's own face when they are not names. */
export const SansLinks: Story = {
  args: {
    monoLinks: false,
    parts: [
      { text: 'Whether the break holds is the job of ' },
      { text: 'Failed breakout', href: '/guide/playbooks/failed_breakout' },
      { text: '.' },
    ],
  },
};

/** No links: just the paragraph, in the chosen tone and size. */
export const NoLinks: Story = {
  args: { parts: [{ text: 'The guide names no field here.' }], tone: 'secondary', size: 'sm' },
};

/** A list of short caveats at the small size. */
export const Dense: Story = {
  render: () => (
    <Stack gap={1}>
      {[CAVEAT, CAVEAT.slice(0, 3)].map((parts, index) => (
        <LinkedProse key={index} parts={parts} size="sm" tone="secondary" monoLinks />
      ))}
    </Stack>
  ),
};

/** Long text wraps like any paragraph; links wrap with it. */
export const LongText: Story = {
  args: { parts: [...CAVEAT, { text: ' ' }, ...CAVEAT] },
  decorators: [
    (Story) => (
      <div style={{ maxWidth: '36ch' }}>
        <Story />
      </div>
    ),
  ],
};
