import type { Meta, StoryObj } from '@storybook/react-vite';

import type { EventItem } from '../EventChip';
import { cpi, dayAfter, earnings, fomc, opex, results } from '../../testing';
import { ExpiryLadder, type ExpiryRow } from './ExpiryLadder';

/** The listed expiries of NVDA on Fri 2 Oct 2026 (sample): weeklies, then the monthlies. */
const spans = (expiry: string, all: readonly EventItem[]) => all.filter((e) => e.date <= expiry);
const ahead: EventItem[] = [cpi, opex, earnings, fomc];
const expiries: [string, number][] = [
  ['2026-10-09', 7],
  ['2026-10-16', 14],
  ['2026-10-23', 21],
  ['2026-10-30', 28],
  ['2026-11-20', 49],
  ['2026-12-18', 77],
];

function toRows(list: readonly [string, number][], all: readonly EventItem[]): ExpiryRow[] {
  let seenClear = false;
  return list.map(([expiry, dte]) => {
    const events = spans(expiry, all);
    const clear = events.length === 0;
    const firstClear = clear && !seenClear;
    seenClear ||= clear;
    return { expiry, dte, events, clear, firstClear };
  });
}

const meta = {
  title: 'Components/ExpiryLadder',
  component: ExpiryLadder,
  args: { label: 'NVDA expiries, 7 to 90 days', rows: toRows(expiries, ahead) },
} satisfies Meta<typeof ExpiryLadder>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The 9 Oct expiry spans nothing, so it is the first clear row; the later ones span the 14 Oct CPI and more. */
export const Default: Story = {};

/** An early filing sits before every expiry: no row is clear, so none is marked. */
export const NoClearRow: Story = {
  args: { rows: toRows(expiries, [{ ...results, date: '2026-10-06' }]) },
};

export const Loading: Story = { args: { status: 'loading' } };

export const Empty: Story = { args: { rows: [] } };

export const Error: Story = {
  args: {
    status: 'error',
    errorMessage: 'The chain for Fri 2 Oct could not load.',
    onRetry: () => undefined,
  },
};

/** Fifteen weekly and monthly expiries with several events each. */
export const Dense: Story = {
  args: {
    rows: toRows(
      Array.from(
        { length: 13 },
        (_, week) => [dayAfter(week * 7 + 7), week * 7 + 7] as [string, number],
      ),
      [
        cpi,
        opex,
        earnings,
        fomc,
        { ...cpi, date: '2026-11-12', label: 'CPI' },
        { ...opex, date: '2026-11-20' },
        { ...fomc, date: '2026-12-09' },
      ],
    ),
  },
};
