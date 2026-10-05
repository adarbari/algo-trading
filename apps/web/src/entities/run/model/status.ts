/**
 * What a recorded status means on screen: the tone of an item status code (OK, STALE_DATA,
 * NO_CHAIN, FETCH_ERROR, ...), of a run or nightly step (complete / succeeded / waived / failed /
 * not run, ADR 0039) and of a check (PASS /
 * WARN / FAIL), and a one-line hint for the item codes admins see most. The text always says
 * the status; the tone only reinforces it.
 */
import type { DataTone, StatusTone } from '@algotrade/ui';

const POSITIVE = new Set(['OK', 'STORED', 'PASS', 'COMPLETE', 'COMPLETED', 'SUCCEEDED']);
const WARNING = new Set([
  'WARN',
  'PARTIAL',
  'STALE_DATA',
  'RUNNING',
  'QUEUED',
  'CARRIED',
  'WAIVED',
]);
const NEGATIVE = new Set(['FAIL', 'FAILED', 'ERROR', 'FETCH_ERROR', 'NOT_ATTEMPTED', 'NOT_RUN']);

/** The tone of a status (any case), for StatusBadge. */
export function statusTone(status: string): StatusTone {
  const code = status.split(':', 1)[0]?.trim().toUpperCase() ?? '';
  if (POSITIVE.has(code)) return 'positive';
  if (WARNING.has(code) || code.startsWith('STALE')) return 'warning';
  if (NEGATIVE.has(code) || code.endsWith('_ERROR')) return 'negative';
  return 'neutral';
}

/** The tone of a status as a data segment (StackedBar, Legend): neutral reads as muted. */
export function segmentTone(status: string): DataTone {
  const tone = statusTone(status);
  return tone === 'neutral' || tone === 'accent' ? 'muted' : tone;
}

const HINTS: Record<string, string> = {
  STALE_DATA:
    "The vendor's latest data is from an earlier session (thin names with no trades); screens treat them as UNKNOWN.",
  NO_CHAIN: 'No option chain is published for these underlyings.',
  NO_STANDARD_SERIES: 'Only non-standard (adjusted) option series are listed.',
  FETCH_ERROR: 'The vendor request failed after retries; a re-run fetches these again.',
  NOT_ATTEMPTED: 'The run stopped before reaching these items.',
};

/** A short explanation of an item status code, when there is one. */
export function statusHint(status: string): string | undefined {
  return HINTS[status.split(':', 1)[0]?.trim().toUpperCase() ?? ''];
}
