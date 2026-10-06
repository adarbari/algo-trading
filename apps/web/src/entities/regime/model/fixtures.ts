/**
 * Test builders for the regime entity (exported for widget and page tests): a `Regime` with three indicator cards (two slow, one
 * fast; one changed; two cite the same link) and the same regime as an UNKNOWN session.
 */
import type { Regime } from './regime';

const NO_UNKNOWN = null;

export function regimeFixture(overrides: Partial<Regime> = {}): Regime {
  return {
    session: '2026-10-02',
    label: 'CAUTION',
    headline: '1 of 3 warning signs is on. The fast signs are quiet.',
    scores: {
      macroRisk: { value: 62, unknown: NO_UNKNOWN },
      marketStress: { value: 18, unknown: NO_UNKNOWN },
      fragility: { value: 40, unknown: NO_UNKNOWN },
    },
    sizing: {
      label: 'CAUTION',
      multiplier: 0.75,
      enabled: true,
      multipliers: [
        { label: 'CALM', multiplier: 1 },
        { label: 'CAUTION', multiplier: 0.75 },
        { label: 'STRESS', multiplier: 0.5 },
        { label: 'CRISIS', multiplier: 0.25 },
      ],
      unknownMultiplier: 0,
      screeners: [
        { screenerId: 'momentum', name: 'Momentum', enabled: true, pauseIn: ['CRISIS'] },
        {
          screenerId: 'vrp_scanner',
          name: 'VRP scanner',
          enabled: true,
          pauseIn: ['STRESS', 'CRISIS'],
        },
        { screenerId: 'quiet', name: 'Quiet', enabled: true, pauseIn: [] },
      ],
    },
    unknownReason: NO_UNKNOWN,
    indicators: [
      {
        key: 'curve_10y3m',
        pace: 'slow',
        plainName: 'Is the yield curve inverted?',
        technicalName: '10y minus 3m Treasury spread',
        oneLiner: 'Long rates below short rates.',
        whyItMatters: 'An inverted curve has come before every recent recession.',
        whatOnMeans: 'Banks earn less on lending, so they lend less.',
        before: [
          { episode: '2008', line: 'Inverted for 16 months before the fall.' },
          { episode: '2022', line: 'Inverted for 20 months; no recession followed yet.' },
        ],
        leadTime: '6 to 24 months',
        falseAlarms: 'Few, but it can be early by two years.',
        links: [
          { title: 'FRED: 10y minus 3m spread', url: 'https://fred.stlouisfed.org/series/T10Y3M' },
        ],
        value: -0.31,
        unknown: NO_UNKNOWN,
        format: 'NUMBER',
        status: 'OFF',
        changed: false,
      },
      {
        key: 'nfci',
        pace: 'slow',
        plainName: 'Are financial conditions tight?',
        technicalName: 'Chicago Fed NFCI',
        oneLiner: 'How hard it is to borrow.',
        whyItMatters: 'Tight money slows spending.',
        whatOnMeans: 'Credit is harder to get than usual.',
        before: [],
        leadTime: 'Months',
        falseAlarms: 'Noisy around crises that do not spread.',
        links: [{ title: 'Chicago Fed NFCI', url: 'https://www.chicagofed.org/nfci' }],
        value: 0.3,
        unknown: NO_UNKNOWN,
        format: 'NUMBER',
        status: 'ON',
        changed: true,
      },
      {
        key: 'vix_term',
        pace: 'fast',
        plainName: 'Is fear rising?',
        technicalName: 'VIX term structure',
        oneLiner: 'Short-term fear above long-term fear.',
        whyItMatters: 'Traders pay up for protection before they sell.',
        whatOnMeans: 'Short-dated volatility is above long-dated volatility.',
        before: [{ episode: '2020', line: 'Flipped a week before the fall.' }],
        leadTime: 'Days',
        falseAlarms: 'Several a year.',
        links: [{ title: 'Chicago Fed NFCI', url: 'https://www.chicagofed.org/nfci' }],
        value: null,
        unknown: { code: 'NO_PARTITION', detail: 'no market row for 2026-10-02' },
        format: 'NUMBER',
        status: 'UNKNOWN',
        changed: null,
      },
    ],
    ...overrides,
  };
}

/** The same session before the regime exists in the catalogue (RG3): UNKNOWN with its reason. */
export function unknownRegimeFixture(): Regime {
  const known = regimeFixture();
  return regimeFixture({
    label: 'UNKNOWN',
    headline: 'Not computed yet',
    scores: {
      macroRisk: { value: null, unknown: { code: 'NOT_IN_CATALOGUE', detail: 'regime not built' } },
      marketStress: {
        value: null,
        unknown: { code: 'NOT_IN_CATALOGUE', detail: 'regime not built' },
      },
      fragility: { value: null, unknown: { code: 'NOT_IN_CATALOGUE', detail: 'regime not built' } },
    },
    sizing: { ...known.sizing, label: 'UNKNOWN', multiplier: null },
    unknownReason: { code: 'NOT_IN_CATALOGUE', detail: 'The regime is not in the catalogue yet.' },
    indicators: known.indicators.map((i) => ({
      ...i,
      value: null,
      unknown: { code: 'NOT_IN_CATALOGUE', detail: 'not stored for this session' },
      status: 'UNKNOWN' as const,
      changed: null,
    })),
  });
}
