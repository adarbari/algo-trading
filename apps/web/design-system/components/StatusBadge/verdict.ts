/**
 * Verdict tone map: the one tint of each setup verdict badge (Works, Promising, Too few cases,
 * Baseline, No better than chance). The words are the caller's; colour only reinforces them.
 */
import type { StatusTone } from './StatusBadge';

export type VerdictKey =
  'works' | 'promising' | 'too_few_cases' | 'baseline' | 'no_better_than_chance';

const VERDICT_TONE: Record<VerdictKey, StatusTone> = {
  works: 'positive',
  promising: 'accent',
  too_few_cases: 'warning',
  baseline: 'neutral',
  no_better_than_chance: 'neutral',
};

/** The badge tone of a verdict; a verdict this map does not know reads neutral. */
export function verdictTone(verdict: string): StatusTone {
  return verdict in VERDICT_TONE ? VERDICT_TONE[verdict as VerdictKey] : 'neutral';
}
