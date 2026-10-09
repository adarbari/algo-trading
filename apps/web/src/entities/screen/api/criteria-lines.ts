/**
 * One screener's criteria as lines (label, rule in the field's format, mode): the typed criteria
 * of its `Screener` (the Screeners list's run summary) through the catalogue, the same rule
 * source the scorecard reads. No query of its own.
 */
import { useMemo } from 'react';

import { byName, useFeatureCatalogue } from '@/entities/feature';

import {
  criterionLines,
  toCriteria,
  type CriterionLine,
  type ServedCriterion,
} from '../model/criteria-lines';

export function useCriterionLines(criteria: readonly ServedCriterion[] | undefined): {
  lines: CriterionLine[];
  isPending: boolean;
} {
  const catalogue = useFeatureCatalogue();
  const features = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const lines = useMemo(() => criterionLines(toCriteria(criteria), features), [criteria, features]);
  return { lines, isPending: catalogue.isPending };
}
