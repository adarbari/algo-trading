/**
 * A screener's criteria as lines for a list: each one's catalogue label, its rule (operator and
 * threshold in the field's own format, the same `describeRule` the scorecard uses) and its mode.
 * Pure.
 */
import { featureLabel, type CatalogueFeature } from '@/entities/feature';

import { describeRule } from './rule';
import type { Criterion } from './spec';

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
