import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { SessionStrip, type SessionStripItem } from './SessionStrip';

/** Ten sessions: a gap, a partial run, then complete runs; the last is the one shown. */
const TEN: SessionStripItem[] = [
  { label: 'Oct 9: Complete, 14 picked', tone: 'positive' },
  { label: 'Oct 12: Complete, 13 picked', tone: 'positive' },
  { label: 'Oct 13: Not run', tone: 'muted' },
  { label: 'Oct 14: Partial, 9 picked', tone: 'warning' },
  { label: 'Oct 15: Complete, 12 picked', tone: 'positive' },
  { label: 'Oct 16: Complete, 12 picked', tone: 'positive' },
  { label: 'Oct 19: Complete, 11 picked', tone: 'positive' },
  { label: 'Oct 20: Complete, 12 picked', tone: 'positive' },
  { label: 'Oct 21: Complete, 15 picked', tone: 'positive' },
  { label: 'Oct 22: Complete, 15 picked', tone: 'positive', current: true },
];

const meta = {
  title: 'Components/SessionStrip',
  component: SessionStrip,
  args: { items: TEN, label: 'Last 10 sessions' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a strip draws the sessions it is given; the page around it loads',
        Error: 'a strip draws the sessions it is given; the page around it fails',
      },
    },
  },
} satisfies Meta<typeof SessionStrip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Nothing ran: every square is an empty dashed one, never a coloured one. */
export const NeverRan: Story = {
  args: { items: TEN.map((i) => ({ ...i, label: 'Not run', tone: 'muted' as const })) },
};

/** No sessions: nothing is drawn, the list keeps its name. */
export const Empty: Story = { args: { items: [] } };

/** A long history wraps onto more lines instead of widening the row. */
export const Dense: Story = {
  args: {
    items: Array.from({ length: 40 }, (_, i) => ({
      label: `Session ${String(i + 1)}: Complete, 12 picked`,
      tone: i % 7 === 3 ? ('muted' as const) : ('positive' as const),
    })),
    label: 'Last 40 sessions',
  },
};

export const Narrow: Story = { decorators: [narrow] };
