/**
 * The facts of the ticker page's "Where a ticker stands" cards, as rows from the instrument's
 * facts for the session (`InstrumentFacts`): the avoid-list checks (a late-filing notice, a
 * lock-up expiry, the share count, short interest) and the next report with the move the options
 * market prices for it. Every value is the server's, formatted with its `info.format`; a fact
 * the session has no partition for says Unknown with the reason, and one with nothing on file
 * says None with what that means. Nothing is judged here: the marks are the reader's.
 */
import type { KeyValueItem } from '@algotrade/ui';

import { factItem, type FactSpec, type Values } from '@/entities/feature';
import { feature, type SiteFeature } from '@/shared/api';

/** The avoid-list checks, in the order the card lists them. */
export const CHECKS: readonly FactSpec[] = [
  {
    id: 'late',
    label: 'Sessions since a late-filing notice',
    name: feature('rollup.filing_events@v1.sessions_since_late_filing'),
  },
  {
    id: 'lockup',
    label: 'Sessions to a lock-up expiry',
    name: feature('rollup.ipo_lockups@v1.sessions_to_lockup_expiry'),
  },
  {
    id: 'shares',
    label: 'Share count, change over a year',
    name: feature('feature.shares_change_yoy'),
    signed: true,
  },
  {
    id: 'short',
    label: 'Short interest, days to cover',
    name: feature('rollup.short_interest@v1.days_to_cover'),
  },
];

/** The next report and its priced move. */
export const NEXT: readonly FactSpec[] = [
  {
    id: 'date',
    label: 'Next report',
    name: feature('rollup.earnings@v1.next_earnings_date'),
  },
  {
    id: 'move',
    label: 'Options-priced move',
    name: feature('rollup.implied_move@v1.implied_move'),
  },
  {
    id: 'expiry',
    label: 'To the expiry of',
    name: feature('rollup.implied_move@v1.move_expiry'),
  },
];

export const STANDS_FEATURES: readonly SiteFeature[] = [...CHECKS, ...NEXT].map((f) => f.name);

/**
 * One row per spec: the value; Unknown with the reason; or None with what a missing value means
 * for the feature (the server's `nullMeaning`), so a check never silently disappears.
 */
export function rows(values: Values, specs: readonly FactSpec[]): KeyValueItem[] {
  return specs.map((spec) => {
    const item = factItem(values, spec);
    if (item) return item;
    const served = values.get(spec.name);
    return {
      id: spec.id,
      label: spec.label,
      value: served ? 'None' : 'Unknown',
      hint: served ? (served.info.nullMeaning ?? undefined) : undefined,
    };
  });
}
