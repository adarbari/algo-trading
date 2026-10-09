/**
 * A pick's criteria as the scorecard's rows: the field's label, the value judged in the field's
 * own format, the rule from the screen's criterion (operator and threshold, in the field's
 * unit), the outcome and, for a near miss or a miss, how far from passing in that same format.
 * Every number is served (the run's value and distance); nothing is counted or recomputed. Pure.
 */
import { formatValue } from '@algotrade/ui';

import {
  displayValue,
  featureFormat,
  featureLabel,
  type CatalogueFeature,
} from '@/entities/feature';

import { describeRule } from './rule';
import type { Criterion } from './spec';

/** One criterion as a run stored it for one instrument (`CriterionResult`). */
export interface ScorecardEntry {
  id: string;
  field: string;
  /** PASS / NEAR / FAIL / MISSING (MISSING when the run stored nothing for it). */
  outcome: string;
  value?: unknown;
  /** How far from passing (near miss or miss), in the field's unit. */
  distance?: number | null | undefined;
}

export interface ScorecardRow {
  id: string;
  label: string;
  /** The value judged, formatted; an em dash when missing. */
  value: string;
  /** The criterion's rule (`≥ 50%`); "" when the screen's rule is not known. */
  rule: string;
  /** How far from passing, formatted; null when none is served. */
  distance: string | null;
  outcome: string;
}

export function scorecardRows(
  entries: readonly ScorecardEntry[],
  features: ReadonlyMap<string, CatalogueFeature>,
  rules: ReadonlyMap<string, Criterion>,
): ScorecardRow[] {
  return entries.map((entry) => {
    const feature = features.get(entry.field);
    const format = featureFormat(feature);
    const rule = rules.get(entry.id);
    const missing =
      entry.outcome === 'MISSING' || entry.value === null || entry.value === undefined;
    return {
      id: entry.id,
      label: feature ? featureLabel(feature.name) : entry.id,
      value: missing ? '—' : formatValue(displayValue(entry.value), format).text,
      rule: rule ? describeRule(rule, feature) : '',
      distance:
        entry.distance === null || entry.distance === undefined
          ? null
          : formatValue(entry.distance, format).text,
      outcome: entry.outcome,
    };
  });
}
