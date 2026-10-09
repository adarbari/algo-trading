import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { OutcomeDots, type OutcomeDot } from './OutcomeDots';

/** Sample criteria of one pick, one square each. */
const MIXED: OutcomeDot[] = [
  { label: 'Trend: Passed', tone: 'positive' },
  { label: 'Volume: Passed', tone: 'positive' },
  { label: 'IV rank: Near miss', tone: 'warning' },
  { label: 'Spread: Missed', tone: 'negative' },
  { label: 'Earnings gap: No value', tone: 'muted' },
];

const meta = {
  title: 'Components/OutcomeDots',
  component: OutcomeDots,
  args: { items: MIXED, label: 'Criteria' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a row of squares draws the outcomes it is given; the table around it loads',
        Error: 'a row of squares draws the outcomes it is given; the table around it fails',
      },
    },
  },
} satisfies Meta<typeof OutcomeDots>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** No items: nothing is drawn, the label still reads "none". */
export const Empty: Story = { args: { items: [] } };

/** Many criteria wrap onto a second line instead of widening the cell. */
export const Dense: Story = {
  args: {
    items: Array.from({ length: 24 }, (_, i) => ({
      label: `Criterion ${String(i + 1)}: Passed`,
      tone: i % 5 === 0 ? ('negative' as const) : ('positive' as const),
    })),
  },
};

export const Narrow: Story = { decorators: [narrow] };
