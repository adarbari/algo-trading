/**
 * How a screen decision and a criterion outcome read, in one place for every table and badge:
 * a decision's words and badge tone, and the tint behind a criterion's cell (a near miss or a
 * miss; the cell's text still says which).
 */
import type { DataTableFill } from '@algotrade/ui';

/** "EVENT_RISK" -> "Event risk". */
export function decisionLabel(decision: string): string {
  const text = decision.toLowerCase().replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type DecisionTone = 'positive' | 'accent' | 'warning' | 'neutral';

/** QUALIFIED positive, WATCH accent, EVENT_RISK warning; the rest (SKIPPED, REJECT) neutral. */
export function decisionTone(decision: string): DecisionTone {
  if (decision === 'QUALIFIED') return 'positive';
  if (decision === 'WATCH') return 'accent';
  if (decision === 'EVENT_RISK') return 'warning';
  return 'neutral';
}

/** The tint of a criterion's cell by its outcome (PASS: none). */
export const OUTCOME_FILL: Readonly<Record<string, DataTableFill>> = {
  NEAR: 'warning',
  FAIL: 'negative',
  MISSING: 'negative',
};
