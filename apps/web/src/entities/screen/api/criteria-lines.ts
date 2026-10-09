/**
 * One screener's criteria as lines (label, rule in the field's format, mode): its resolved
 * working copy through the catalogue, the same rule source the scorecard reads.
 */
import { useMemo } from 'react';

import { byName, useFeatureCatalogue } from '@/entities/feature';

import { criterionLines, type CriterionLine } from '../model/criteria-lines';
import { criteriaOf } from '../model/spec';
import { useScreener } from './hooks';

export function useCriterionLines(screenerId: string): {
  lines: CriterionLine[];
  isPending: boolean;
} {
  const catalogue = useFeatureCatalogue();
  const detail = useScreener(screenerId);
  const features = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const lines = useMemo(
    () => criterionLines(criteriaOf(detail.data?.resolved, { id: screenerId }), features),
    [detail.data, screenerId, features],
  );
  return { lines, isPending: detail.isPending };
}
