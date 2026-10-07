import type { Meta, StoryObj } from '@storybook/react-vite';

import {
  cpi,
  dayAfter,
  earnings,
  fomc,
  oneOfEach,
  opex,
  referenceEarnings,
  results,
} from '../../testing';
import type { EventItem } from '../EventChip';
import { EventTimeline } from './EventTimeline';

const START = '2026-10-02';
const END = '2026-12-31';

const meta = {
  title: 'Components/EventTimeline',
  component: EventTimeline,
  args: {
    label: 'NVDA events, next 90 days',
    events: [...oneOfEach, fomc],
    start: START,
    end: END,
  },
} satisfies Meta<typeof EventTimeline>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Earnings, a macro release, an expiry day and a filing over the next 90 days; two events share 28 Oct. */
export const Default: Story = {};

export const Loading: Story = { args: { status: 'loading' } };

export const Empty: Story = { args: { events: [] } };

export const Error: Story = {
  args: {
    status: 'error',
    errorMessage: 'The events could not load for Fri 2 Oct.',
    onRetry: () => undefined,
  },
};

/** Many events: a macro release every week and an expiry Friday each month, collapsed to counts. */
const busy: EventItem[] = Array.from({ length: 12 }, (_, week) => [
  { ...cpi, date: dayAfter(week * 7 + 3), label: week % 2 === 0 ? 'CPI' : 'Jobs' },
  ...(week % 3 === 0 ? [{ ...opex, date: dayAfter(week * 7 + 3) }] : []),
  ...(week % 4 === 1 ? [{ ...results, date: dayAfter(week * 7 + 3) }] : []),
]).flat();

export const Dense: Story = {
  args: { events: [earnings, referenceEarnings, ...busy], dense: true },
};

/** The same many events, one chip each. */
export const Expanded: Story = { args: { events: [earnings, referenceEarnings, ...busy] } };
