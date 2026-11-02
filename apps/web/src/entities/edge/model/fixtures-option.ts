/** Fixtures of an option setup's page read, for stories and tests (the shape of `edgeOptionSetup`). */
import type { OptionEvidence, OptionSetup } from './option-setup';

const unknownNote = {
  code: 'LICENCE',
  kind: 'LICENCE',
  guideTerm: 'unavailable_licence',
  kindText: 'Not available to your account',
} as const;

const EVIDENCE: OptionEvidence = {
  unknown: null,
  basisScreener: 'iv_rich_puts',
  trades: 100,
  typical: 0.012,
  typicalLo: -0.004,
  typicalHi: 0.021,
  badMean: -0.083,
  badTrades: 5,
  kept: 72,
  inSampleOnly: false,
  costs: {
    state: 'measured',
    assumedBp: 10,
    levels: [
      { period: 'all', bp: 10, assumed: true, level: 'mid', meanRoc: 0.0102, winRate: 0.72 },
      { period: 'all', bp: 10, assumed: false, level: 'effective', meanRoc: 0.0071, winRate: 0.7 },
      { period: 'all', bp: 10, assumed: false, level: 'full', meanRoc: 0.0032, winRate: 0.66 },
    ],
  },
  byYear: [
    { year: 2024, trades: 48, typical: 0.011, kept: 35 },
    { year: 2025, trades: 52, typical: 0.013, kept: 37 },
  ],
  stress: [
    {
      key: 'covid_2020',
      name: 'Covid crash',
      start: '2020-02-19',
      end: '2020-03-23',
      trades: 0,
      worst: null,
    },
    {
      key: 'rates_2022',
      name: 'Rate shock',
      start: '2022-01-03',
      end: '2022-10-12',
      trades: 6,
      worst: -0.092,
    },
  ],
  stressUnknown: null,
};

export const OPTION_SETUP_FIXTURE: OptionSetup = {
  edgeId: 'put_write_weekly',
  positionKind: 'options',
  rulesUnknown: null,
  rules: {
    template: 'cash_secured_put',
    collateral: 'cash_secured',
    schedule: 'every_session',
    startOffsetSessions: 1,
    tenorDays: 30,
    expiryCycle: 'monthly',
    skipReportInLife: true,
    takeProfit: 0.5,
    stopLoss: 2,
    exitDte: 21,
    exitConditionFields: ['iv_rank'],
    caseValued: ['strike'],
    legs: [
      {
        kind: 'option',
        qty: -1,
        right: 'P',
        strike: 'delta',
        delta: 0.3,
        otmPct: null,
        tenorDays: null,
      },
    ],
  },
  evidence: EVIDENCE,
};

export const OPTION_SETUP_HIDDEN_FIXTURE: OptionSetup = {
  ...OPTION_SETUP_FIXTURE,
  evidence: {
    ...EVIDENCE,
    unknown: unknownNote,
    trades: 0,
    typical: null,
    typicalLo: null,
    typicalHi: null,
    badMean: null,
    badTrades: 0,
    kept: 0,
    costs: null,
    byYear: [],
    stress: [],
  },
};

export const SHARE_SETUP_FIXTURE: OptionSetup = {
  edgeId: 'momentum_12_1',
  positionKind: 'shares',
  rules: null,
  rulesUnknown: null,
  evidence: null,
};
