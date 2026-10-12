/**
 * What a pending row says of the criterion a proposed formula waits to join the screen with: the
 * field it will read and its operator and threshold as one short line. Pure.
 */
import { operatorSymbol, shapeOf } from '@/entities/feature';
import type { components } from '@/shared/api';

type Formula = components['schemas']['DraftFormula'];

export interface PendingLine {
  /** The field the criterion reads (the formula's own feature when it has no criterion field). */
  name: string;
  /** `>= -0.05`; empty when the criterion has none to show. */
  summary: string;
}

export function pendingLine(formula: Formula): PendingLine | null {
  const criterion = formula.criterion;
  if (!criterion) return null;
  const field = criterion['field'];
  const op = criterion['op'];
  const value: unknown = criterion['value'];
  const one = (v: unknown): string =>
    typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' ? String(v) : '';
  const shown = Array.isArray(value) ? value.map(one).join(' and ') : one(value);
  const symbol = typeof op === 'string' ? operatorSymbol(op) : '';
  const bare = typeof op === 'string' && shapeOf(op) === 'none';
  return {
    name: typeof field === 'string' ? field : `feature.${formula.name}`,
    summary: bare ? symbol : [symbol, shown].filter((part) => part !== '').join(' '),
  };
}
