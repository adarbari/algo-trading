/**
 * The tone of a status badge in the Financials panel, by the status words the financials and
 * analyst rollups store (OK, PARTIAL, STALE, NO_TTM, NO_FACTS, NOT_COVERED, NOT_FETCHED, BUILDING,
 * NO_PRIOR, FINANCIAL). Only OK reads positive and a stale or partial figure warns; a source
 * that has nothing for the name (NOT_COVERED, NOT_FETCHED) or no history yet (BUILDING, NO_PRIOR)
 * is not a fault, so it stays neutral. Kept in the panel's own
 * model so the lazy panel chunk imports nothing shared with the admin pages. The word on the
 * badge always says the status; the tone only reinforces it.
 */
import type { StatusTone } from '@algotrade/ui';

const TONES: Readonly<Record<string, StatusTone>> = {
  OK: 'positive',
  PARTIAL: 'warning',
  STALE: 'warning',
};

/** The tone for a served status word (any case); an unlisted word or a gap is neutral. */
export function financialsTone(word: string): StatusTone {
  return TONES[word.trim().toUpperCase()] ?? 'neutral';
}
