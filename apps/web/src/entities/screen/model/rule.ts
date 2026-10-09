/**
 * A criterion read as a sentence ("IV30 ≥ 50%"), built from its field, operator and threshold in
 * the field's unit, so it can never disagree with the rule it names (a stored label can).
 * Pure.
 */
import {
  featureTitle,
  fieldKind,
  operatorSymbol,
  scaleOf,
  shapeOf,
  toTyped,
  type CatalogueFeature,
  type NumberScale,
} from '@/entities/feature';

import type { Criterion } from './spec';

const MAX_DIGITS = 4;

function typed(value: unknown, scale: NumberScale | null): string {
  if (typeof value === 'number' && scale) {
    const text = toTyped(value, scale).toLocaleString('en-US', {
      maximumFractionDigits: MAX_DIGITS,
    });
    // A word unit ("pts", "days") stands apart from the number; a symbol ("%", "×") does not.
    const gap = scale.suffix && /^[a-z]/i.test(scale.suffix) ? ' ' : '';
    return `${scale.prefix ?? ''}${text}${gap}${scale.suffix ?? ''}`;
  }
  return String(value);
}

/** The rule alone, as the criterion reads after its field: `≥ 50%`, `between 5 and 10`, `is empty`; "" without a threshold. */
export function describeRule(
  criterion: Pick<Criterion, 'field' | 'op' | 'value'>,
  feature: CatalogueFeature | undefined,
): string {
  const shape = shapeOf(criterion.op);
  if (shape === 'none') return criterion.op === 'is_null' ? 'is empty' : 'has a value';
  const scale = fieldKind(feature) === 'number' ? scaleOf(feature) : null;
  const { value } = criterion;
  if (value === undefined || value === null || value === '') return '';
  if (shape === 'list' && Array.isArray(value)) {
    return `${operatorSymbol(criterion.op)} ${value.map((v) => typed(v, scale)).join(', ')}`;
  }
  if (shape === 'range' && Array.isArray(value) && value.length === 2) {
    return `between ${typed(value[0], scale)} and ${typed(value[1], scale)}`;
  }
  return `${operatorSymbol(criterion.op)} ${typed(value, scale)}`;
}

/** `IV30 ≥ 50%`, `Near 52w in HIGH, LOW`, `Close between 5 and 10`, `Sector has a value`. */
export function describeCriterion(
  criterion: Pick<Criterion, 'field' | 'op' | 'value'>,
  feature: CatalogueFeature | undefined,
): string {
  return [featureTitle(criterion.field), describeRule(criterion, feature)]
    .filter(Boolean)
    .join(' ');
}
