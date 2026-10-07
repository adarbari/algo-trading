import type { Meta, StoryObj } from '@storybook/react-vite';

import { CalendarGrid } from './CalendarGrid';
import { expiryFridays, manyNames, names, sampleDays } from '../../testing';

const meta = {
  title: 'Components/CalendarGrid',
  component: CalendarGrid,
  args: {
    label: 'Events, next 90 days: scope list',
    days: sampleDays,
    names,
    ruledDays: expiryFridays,
    orientation: 'days-down',
  },
} satisfies Meta<typeof CalendarGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Four names over the next weeks: earnings, CPI, FOMC and a filing; the expiry Fridays are ruled. */
export const Default: Story = {};

/**
 * `orientation` defaults to `auto`: days down, flipping to days across when the grid is narrower
 * than 720 px. The screenshots are 640 px wide, so the stories force the orientation.
 */
export const DaysAcross: Story = { args: { orientation: 'days-across' } };

export const Loading: Story = { args: { status: 'loading' } };

export const Empty: Story = { args: { days: [] } };

export const Error: Story = {
  args: {
    status: 'error',
    errorMessage: 'The calendar could not load for Fri 2 Oct.',
    onRetry: () => undefined,
  },
};

/** Sixty-four names: 30 per page, Previous / Next names. */
const many = manyNames(64);
export const Dense: Story = {
  args: {
    label: 'Events, next 90 days: 64 names',
    days: many.days,
    names: many.names,
    ruledDays: expiryFridays,
  },
};
