/**
 * The Edges section's reads as the server answers them, for tests: an edge row, a mechanism, a
 * site edge's page and an idea, with the prose split into segments as `GuideProse` is.
 */
const prose = (text: string) => ({ text, segments: [{ text, field: null }] });

export const edgeRow = (over: Record<string, unknown> = {}) => ({
  id: 'earnings_date_advance',
  name: 'Earnings-date advances',
  thesis: 'Stocks whose next earnings date moves a week earlier outperform the next month.',
  mechanism: 'slow_to_update',
  asset: 'stocks',
  assetText: 'Stocks',
  side: 'long',
  sideTerm: 'side_long',
  holdingSessions: [20],
  holdingText: '20 sessions',
  holdingBand: 'medium',
  status: 'candidate',
  ...over,
});

export const idea = (over: Record<string, unknown> = {}) => ({
  id: 'lazy_prices_10k_change',
  title: 'Year-on-year change in filing text',
  mechanism: 'slow_to_update',
  verdict: 'strong',
  verdictText: 'Strong',
  feasibilityText: 'Needs data',
  feasibilityTerm: 'idea_feasibility',
  whyNotBuilt: 'Filing text is not ingested yet.',
  ...over,
});

export const mechanism = (over: Record<string, unknown> = {}) => ({
  id: 'slow_to_update',
  title: 'Slow to update',
  question: 'Who is slow to update?',
  examples: 'post-earnings drift, 12-1 momentum',
  short: 'Prices absorb news in steps, not at once.',
  howItWorks: [prose('A company reports and the price moves, but not all the way.')],
  whyItSurvives: [prose('Arbitrage is expensive to run.'), prose('The behaviour is old.')],
  research: [prose('Jegadeesh and Titman find winners beat losers.')],
  realVsDecoy: [prose('A real edge beats plain momentum.')],
  dont: prose('Do not read a momentum win rate as steady income.'),
  seeAlso: ['edge_how_sure'],
  stats: [
    { title: 'Our bar', value: 't > 3', reading: 'Works needs t above 3.', source: null },
    {
      title: 'Decline after publication',
      value: '-58%',
      reading: 'Average, 97 predictors.',
      source: 1,
    },
  ],
  sources: [
    {
      title:
        'McLean and Pontiff (2016), Does Academic Research Destroy Stock Return Predictability?',
      url: 'https://example.org/mclean',
      reading: 'How much published anomalies decay.',
    },
  ],
  edges: [edgeRow()],
  notBuilt: [idea()],
  ...over,
});

export const edgeEntry = (over: Record<string, unknown> = {}) => ({
  summary: edgeRow(),
  mechanism: { id: 'slow_to_update', title: 'Slow to update' },
  thesis: prose('Stocks whose next earnings date moves a week earlier outperform the next month.'),
  otherSide: prose('Investors who read the date notice as a calendar item.'),
  lasts: prose('A small signal with a few weeks of life each quarter.'),
  research: {
    measure: 'Published spread, advancers against delayers',
    figure: '2.6%',
    expect: '0.4 to 0.6%',
    haircut: 'one third off, long only',
    horizonText: 'the month after the date is known',
    leg: 'long side',
    sample: '25 years',
    source: 'Johnson and So (2018)',
    terms: ['published_haircut'],
  },
  tests: [
    { key: 'outcome', title: 'Outcome', text: 'Excess return over SPY', term: 'excess_return' },
    { key: 'universe', title: 'Universe', text: 'Common stocks above $5', term: null },
  ],
  playbooks: [{ id: 'earnings_date_shift', name: 'Earnings date moved earlier', family: 'Events' }],
  fields: ['feature.days_since_date_shift'],
  failureModes: prose('A fiscal-year change looks like news and is not.'),
  decoys: prose('Plain momentum or size.'),
  rejection: null,
  capacity: prose('Yes, at an individual size.'),
  sources: [
    {
      title: 'Johnson and So (2018), Time Will Tell',
      url: 'https://example.org/js',
      form: 'Paper',
    },
    { title: 'A vendor note', url: null, form: 'Source' },
  ],
  related: [
    edgeRow({
      id: 'momentum_at_earnings',
      name: 'Momentum at earnings',
      thesis: 'Winners going into a report keep winning.',
    }),
  ],
  seeAlso: ['base_rate'],
  ...over,
});

export const edgeIndex = (over: Record<string, unknown> = {}) => ({
  mechanisms: [
    {
      id: 'slow_to_update',
      title: 'Slow to update',
      question: 'Who is slow to update?',
      short: 'Prices absorb news in steps, not at once.',
      examples: 'post-earnings drift',
      count: 2,
      ideas: 1,
      statuses: [{ status: 'candidate', count: 2 }],
      edges: [
        edgeRow(),
        edgeRow({
          id: 'etf_flow',
          name: 'ETF flow drift',
          asset: 'etfs',
          assetText: 'ETFs and funds',
          holdingBand: 'short',
          side: 'long_short',
        }),
      ],
    },
    {
      id: 'forced_flows',
      title: 'Forced buyers and sellers',
      question: 'Who has to trade, whatever the price?',
      short: 'Index funds and margin calls trade on rules, not views.',
      examples: 'index changes',
      count: 1,
      ideas: 0,
      statuses: [{ status: 'blocked', count: 1 }],
      edges: [
        edgeRow({
          id: 'index_adds',
          name: 'Index additions',
          mechanism: 'forced_flows',
          status: 'blocked',
        }),
      ],
    },
  ],
  filters: {
    assets: [
      { id: 'stocks', text: 'Stocks', count: 2 },
      { id: 'etfs', text: 'ETFs and funds', count: 1 },
    ],
    sides: [
      { id: 'long', text: 'Long', count: 2 },
      { id: 'long_short', text: 'Long and short', count: 1 },
    ],
    holdings: [
      { id: 'short', text: 'Days', count: 1 },
      { id: 'medium', text: 'Weeks', count: 2 },
    ],
  },
  setAsideTitle: 'Checked and set aside',
  setAsidePurpose: 'Filed, then rejected or blocked, with the reason on file.',
  setAside: [
    {
      edge: edgeRow({
        id: 'index_adds',
        name: 'Index additions',
        mechanism: 'forced_flows',
        status: 'blocked',
      }),
      why: prose('Blocked: the index membership history is not licensed.'),
    },
  ],
  notBuiltTitle: 'Researched, not built',
  notBuiltPurpose: 'Ideas from the research pass that are not edges yet.',
  notBuilt: [
    idea(),
    idea({
      id: 'large_cap_pead',
      title: 'Large-cap post-earnings drift',
      verdict: 'dead',
      verdictText: 'Dead',
      whyNotBuilt: 'Gone in large caps since the mid-2000s.',
    }),
  ],
  ...over,
});
