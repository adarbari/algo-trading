/**
 * The tone of a status badge in the Financials panel, by the status words the financials rollups
 * store (OK, PARTIAL, STALE, NO_TTM, NO_FACTS, NOT_COVERED, FINANCIAL). Kept in the panel's own
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
