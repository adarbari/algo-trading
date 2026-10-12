/** Test builders for the accepted-formula entity (exported for widget tests): rows as the API answers them. */
import { feature } from '@/shared/api';

import type { AcceptedFormula, AcceptedFormulaList } from './types';

export const formula = (over: Partial<AcceptedFormula> = {}): AcceptedFormula => ({
  fingerprint: 'a1b2c3d4e5f6',
  canonical: '(close / sma_20) - 1',
  expression: 'close/sma_20 - 1',
  unit: 'ratio',
  description: 'Distance of the close from its 20-session average',
  acceptedCount: 4,
  users: 3,
  firstAccepted: '2026-09-02',
  lastAccepted: '2026-10-09',
  duplicateOf: '',
  backlogKey: '',
  ...over,
});

export const FORMULAS_FIXTURE: AcceptedFormulaList = {
  today: '2026-10-11',
  days: 365,
  rows: [
    formula(),
    formula({
      fingerprint: 'b2c3d4e5f6a1',
      canonical: 'high - low',
      expression: 'high - low',
      unit: 'price',
      description: 'Day range',
      acceptedCount: 2,
      users: 2,
      duplicateOf: feature('rollup.momentum@v1.rsi_14'),
      backlogKey: 'day_range',
    }),
    formula({
      fingerprint: 'c3d4e5f6a1b2',
      canonical: 'volume / avg_volume_20',
      expression: 'volume / avg_volume_20',
      unit: 'ratio',
      description: '',
      acceptedCount: 1,
      users: 1,
      lastAccepted: '2026-10-01',
    }),
  ],
};
