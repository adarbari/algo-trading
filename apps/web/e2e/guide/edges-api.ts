/**
 * The Guide's Edges section for the end-to-end tests (a mock of what the server reads from
 * `config/site/guide/mechanisms/` and the site edge documents): `Query.guideEdgeIndex` (two
 * mechanisms, the filters, one edge set aside, two ideas not built), a mechanism and an edge as
 * the batched `Query.guideEntries` answers them, and the index's mechanism list.
 */
type Json = Record<string, unknown>;

const prose = (text: string): Json => ({ text, segments: [{ text, field: null }] });

const row = (over: Json = {}): Json => ({
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

const BLOCKED = row({
  id: 'index_additions',
  name: 'Index additions',
  mechanism: 'forced_flows',
  status: 'blocked',
});

const IDEAS = [
  {
    id: 'lazy_prices',
    title: 'Year-on-year change in filing text',
    mechanism: 'slow_to_update',
    verdict: 'strong',
    verdictText: 'Strong',
    feasibilityText: 'Needs data',
    feasibilityTerm: 'idea_feasibility',
    whyNotBuilt: 'Filing text is not ingested yet.',
  },
  {
    id: 'large_cap_pead',
    title: 'Large-cap post-earnings drift',
    mechanism: 'slow_to_update',
    verdict: 'dead',
    verdictText: 'Dead',
    feasibilityText: 'Buildable',
    feasibilityTerm: 'idea_feasibility',
    whyNotBuilt: 'Gone in large caps since the mid-2000s.',
  },
];

export const MECHANISMS = [
  { id: 'slow_to_update', title: 'Slow to update', count: 1 },
  { id: 'forced_flows', title: 'Forced buyers and sellers', count: 1 },
];

/** The Edges section as `Query.guideIndex` lists it: its entry and the mechanisms. */
export const EDGES_SECTION = {
  id: 'edges',
  title: 'Edges',
  purpose: 'Why an edge should work: the mechanisms, then each edge under its mechanism.',
  entries: 2,
};

export function guideEdgeIndex(): Json {
  return {
    data: {
      guideEdgeIndex: {
        mechanisms: [
          {
            id: 'slow_to_update',
            title: 'Slow to update',
            question: 'Who is slow to update?',
            short: 'Prices absorb news in steps, not at once.',
            examples: 'post-earnings drift, earnings-date advances',
            count: 1,
            ideas: 2,
            statuses: [{ status: 'candidate', count: 1 }],
            edges: [row()],
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
            edges: [BLOCKED],
          },
        ],
        filters: {
          assets: [{ id: 'stocks', text: 'Stocks', count: 2 }],
          sides: [{ id: 'long', text: 'Long', count: 2 }],
          holdings: [{ id: 'medium', text: 'Weeks', count: 2 }],
        },
        setAsideTitle: 'Checked and set aside',
        setAsidePurpose: 'Filed, then rejected or blocked, with the reason on file.',
        setAside: [
          { edge: BLOCKED, why: prose('Blocked: index membership history is not licensed.') },
        ],
        notBuiltTitle: 'Researched, not built',
        notBuiltPurpose: 'Ideas from the research pass that are not edges yet.',
        notBuilt: IDEAS,
      },
    },
  };
}

const MECHANISM = {
  id: 'slow_to_update',
  title: 'Slow to update',
  question: 'Who is slow to update?',
  examples: 'post-earnings drift, earnings-date advances',
  short: 'Prices absorb news in steps, not at once.',
  howItWorks: [prose('A company reports and the price moves, but not all the way.')],
  whyItSurvives: [prose('Arbitrage is expensive to run.'), prose('The behaviour is old.')],
  research: [prose('Past winners beat past losers over three to twelve months.')],
  realVsDecoy: [prose('A real edge beats plain momentum on the same sessions.')],
  dont: prose('Do not read a momentum win rate as steady income.'),
  seeAlso: ['unknown'],
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
  edges: [row()],
  notBuilt: IDEAS,
};

const EDGE = {
  summary: row(),
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
    sample: null,
    source: 'Johnson and So (2018)',
    terms: [],
  },
  tests: [
    { key: 'outcome', title: 'Outcome', text: 'Excess return over SPY', term: 'unknown' },
    { key: 'universe', title: 'Universe', text: 'Common stocks above $5', term: null },
  ],
  playbooks: [{ id: 'vrp_scanner', name: 'VRP scanner', family: 'Option income' }],
  fields: ['rollup.iv30@v1.iv30'],
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
  ],
  related: [],
  seeAlso: ['unknown'],
};

/** The edges a playbook implements (`GuidePlaybookDetail.edges`). */
export const VRP_EDGES = [
  {
    id: 'earnings_date_advance',
    name: 'Earnings-date advances',
    thesis: row()['thesis'],
    status: 'candidate',
  },
];

/** `Query.guideIndex { mechanisms }`: the rail's and the home's list. */
export function guideMechanisms(): Json {
  return { data: { guideIndex: { mechanisms: MECHANISMS } } };
}

/** `Query.guideMechanism(id)`: null for an unknown mechanism. */
export function guideMechanism(id: string): Json {
  return { data: { guideMechanism: id === MECHANISM.id ? MECHANISM : null } };
}

/** `Query.guideEdge(id)`: null for an unknown edge. */
export function guideEdge(id: string): Json {
  return { data: { guideEdge: id === row()['id'] ? EDGE : null } };
}

/** `Query.guidePlaybook(id) { edges }`. */
export function guidePlaybookEdges(id: string): Json {
  return { data: { guidePlaybook: { edges: id === 'vrp_scanner' ? VRP_EDGES : [] } } };
}
