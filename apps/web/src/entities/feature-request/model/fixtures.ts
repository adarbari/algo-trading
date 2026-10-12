/** Test builders for the feature-request entity (exported for widget tests): rows as the API answers them. */
import { feature } from '@/shared/api';

import type { FeatureRequest, FeatureRequestList } from './types';

export const request = (over: Partial<FeatureRequest> = {}): FeatureRequest => ({
  rank: 1,
  ref: 'realised_vol_20d',
  description: 'Realised volatility over 20 sessions',
  feasibility: 'ROLLUP_FROM_STORED',
  score: 2.31,
  users: 3,
  timesAsked: 5,
  firstSeen: '2026-09-02',
  lastSeen: '2026-10-09',
  status: 'OPEN',
  promotedTo: '',
  unmapped: false,
  ...over,
});

export const REQUESTS_FIXTURE: FeatureRequestList = {
  today: '2026-10-11',
  days: 365,
  rows: [
    request(),
    request({
      rank: 2,
      ref: 'short_interest_pct',
      description: 'Short interest as a share of float',
      feasibility: 'NEEDS_SOURCE',
      score: 0.9,
      users: 2,
      timesAsked: 2,
      status: 'OPEN',
    }),
    request({
      rank: 3,
      ref: 'rsi_14',
      description: 'RSI over 14 sessions',
      score: 0.6,
      users: 1,
      timesAsked: 1,
      status: 'PROMOTED',
      promotedTo: feature('rollup.momentum@v1.rsi_14'),
    }),
    request({
      rank: 4,
      ref: 'vibes',
      description: 'How the name feels',
      feasibility: 'UNCLEAR',
      score: 0.1,
      users: 1,
      timesAsked: 1,
      firstSeen: null,
      status: 'UNMAPPED',
      unmapped: true,
    }),
    request({
      rank: 5,
      ref: 'moon_phase',
      description: 'Phase of the moon',
      feasibility: 'UNCLEAR',
      score: 0.05,
      users: 1,
      timesAsked: 1,
      status: 'WONT_DO',
    }),
  ],
};
