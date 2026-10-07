/**
 * Sample events for the event components' stories and tests: a fixed window around Fri 2 Oct
 * 2026 with every kind and time word. Not real data.
 */

/**
 * The shape of an event item, written out here because test support imports no component (the
 * components' own props are checked against it where the samples are used).
 */
export interface SampleEvent {
  date: string;
  time: string;
  kind: 'own_earnings' | 'reference_earnings' | 'macro_release' | 'market_structure' | 'filing';
  label: string;
  source: string;
  knownFrom: string;
}

export const earnings: SampleEvent = {
  date: '2026-10-22',
  time: 'after_hours',
  kind: 'own_earnings',
  label: 'Earnings',
  source: 'Company calendar',
  knownFrom: '2026-09-18',
};

export const referenceEarnings: SampleEvent = {
  date: '2026-10-28',
  time: 'after_hours',
  kind: 'reference_earnings',
  label: 'NVDA earnings',
  source: 'Company calendar',
  knownFrom: '2026-09-30',
};

export const cpi: SampleEvent = {
  date: '2026-10-14',
  time: '08:30',
  kind: 'macro_release',
  label: 'CPI',
  source: 'BLS',
  knownFrom: '2026-01-05',
};

export const fomc: SampleEvent = {
  date: '2026-10-28',
  time: '14:00',
  kind: 'macro_release',
  label: 'FOMC',
  source: 'Federal Reserve',
  knownFrom: '2026-01-05',
};

export const opex: SampleEvent = {
  date: '2026-10-16',
  time: 'unknown',
  kind: 'market_structure',
  label: 'Opex',
  source: 'Exchange calendar',
  knownFrom: '2026-01-02',
};

export const results: SampleEvent = {
  date: '2026-07-30',
  time: 'after_hours',
  kind: 'filing',
  label: '2.02 results',
  source: 'SEC EDGAR',
  knownFrom: '2026-07-30',
};

/** One of each kind. */
export const oneOfEach: SampleEvent[] = [earnings, referenceEarnings, cpi, opex, results];

/** Day offsets from 2 Oct 2026 as ISO days (a helper for the dense stories). */
export function dayAfter(offset: number): string {
  const day = new Date(Date.UTC(2026, 9, 2 + offset));
  return day.toISOString().slice(0, 10);
}
