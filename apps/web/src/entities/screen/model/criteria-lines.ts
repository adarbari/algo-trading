/**
 * A screener's criteria as lines for a list: each one's catalogue label, its rule (operator and
 * threshold in the field's own format, the same `describeRule` the scorecard uses) and its mode.
 * Pure.
 */
import { featureLabel, type CatalogueFeature } from '@/entities/feature';
import type { gqlTypes } from '@/shared/api';

import { describeRule } from './rule';
import { MODES, type Criterion } from './spec';

/** A criterion as the typed `Screener` serves it (`id`, `field`, `mode`, `op`, `value`). */
export type ServedCriterion = gqlTypes.ScreenerRunsQuery['screeners'][number]['criteria'][number];

/** The served criteria as `Criterion`s, in the screen's order (the mode narrowed to the known ones). */
export function toCriteria(served: readonly ServedCriterion[] | undefined): Criterion[] {
  return (served ?? []).map((c) => ({
    id: c.id,
    field: c.field,
    op: c.op,
    mode: MODES.find((m) => m === c.mode) ?? 'hard',
    ...(c.value === null || c.value === undefined ? {} : { value: c.value }),
  }));
}

export interface CriterionLine {
  id: string;
  label: string;
  /** `≥ 50%`, `between 5 and 10`; "" when the criterion has no threshold. */
  rule: string;
  mode: string;
}

export function criterionLines(
  criteria: readonly Criterion[],
  features: ReadonlyMap<string, CatalogueFeature>,
): CriterionLine[] {
  return criteria.map((c) => ({
    id: c.id,
    label: featureLabel(c.field),
    rule: describeRule(c, features.get(c.field)),
    mode: c.mode,
  }));
}
