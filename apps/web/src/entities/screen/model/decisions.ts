/**
 * How a screen decision and a criterion outcome read, in one place for every table and badge:
 * a decision's words and badge tone, and the tint behind a criterion's cell (a near miss or a
 * miss; the cell's text still says which).
 */
import type { DataTableFill, StatusTone } from '@algotrade/ui';

/** "EVENT_RISK" -> "Event risk". */
export function decisionLabel(decision: string): string {
  const text = decision.toLowerCase().replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type DecisionTone = 'positive' | 'accent' | 'warning' | 'neutral';

/**
 * QUALIFIED positive, WATCH accent, EVENT_RISK and PAUSED (held back by the regime gate)
 * warning; the rest (SKIPPED, REJECT) neutral.
 */
export function decisionTone(decision: string): DecisionTone {
  if (decision === 'QUALIFIED') return 'positive';
  if (decision === 'WATCH') return 'accent';
  if (decision === 'EVENT_RISK' || decision === 'PAUSED') return 'warning';
  return 'neutral';
}

/** The tint of a criterion's cell by its outcome (PASS: none). */
export const OUTCOME_FILL: Readonly<Record<string, DataTableFill>> = {
  NEAR: 'warning',
  FAIL: 'negative',
  MISSING: 'negative',
};

const OUTCOME_TONE: Readonly<Record<string, StatusTone>> = {
  PASS: 'positive',
  NEAR: 'warning',
  FAIL: 'negative',
  MISSING: 'negative',
};
const OUTCOME_WORDS: Readonly<Record<string, string>> = {
  PASS: 'Passed',
  NEAR: 'Near miss',
  FAIL: 'Missed',
  MISSING: 'No value',
};

/** The badge tone of a criterion outcome (PASS / NEAR / FAIL / MISSING). */
export function outcomeTone(outcome: string): StatusTone {
  return OUTCOME_TONE[outcome] ?? 'neutral';
}

/** The badge words of a criterion outcome. */
export function outcomeLabel(outcome: string): string {
  return OUTCOME_WORDS[outcome] ?? outcome;
}
