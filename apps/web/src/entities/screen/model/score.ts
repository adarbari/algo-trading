/**
 * How a preview row's score was worked out (ADR 0029, `docs/screeners/rules.md`): 100 minus the
 * penalty of every criterion that missed, clipped to 0..100. One line per penalised criterion,
 * worst first, saying why it cost points. Pure.
 */
import type { PreviewRow } from './preview';

type CriterionValue = PreviewRow['criteria'][number];

export const FULL_SCORE = 100;

export interface ScoreLine {
  criterionId: string;
  field: string;
  /** Points taken off (positive). */
  penalty: number;
  /** Why: "near miss, 40% into the tolerance", "missed", "no value". */
  why: string;
}

export interface ScoreBreakdown {
  score: number | null;
  /** The penalties as summed (before the clip to 0..100). */
  penalties: number;
  /** Below 0 before the clip (many misses tie at 0). */
  clipped: boolean;
  lines: ScoreLine[];
  /** Criteria that passed (no penalty), gates included. */
  passed: number;
}

function why(c: CriterionValue): string {
  if (c.outcome === 'MISSING') return 'no value';
  if (c.outcome === 'NEAR') {
    const into = c.normalised === null ? null : Math.round(c.normalised * 100);
    return into === null ? 'near miss' : `near miss, ${String(into)}% into the tolerance`;
  }
  if (c.mode === 'hard') return 'failed a hard criterion';
  if (c.mode === 'score') return 'missed (a score criterion only costs points)';
  return 'missed beyond the tolerance';
}

export function scoreBreakdown(row: PreviewRow): ScoreBreakdown {
  const lines = row.criteria
    .filter((c) => c.penalty > 0)
    .map((c) => ({ criterionId: c.criterion_id, field: c.field, penalty: c.penalty, why: why(c) }))
    .sort((a, b) => b.penalty - a.penalty);
  const penalties = lines.reduce((sum, line) => sum + line.penalty, 0);
  const passed = row.criteria.filter((c) => c.outcome === 'PASS').length;
  return { score: row.score, penalties, clipped: penalties > FULL_SCORE, lines, passed };
}
