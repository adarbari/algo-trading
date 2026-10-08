/**
 * The Guide's Start here pages, glossary and search for the end-to-end tests (a mock of what the
 * server reads from `start.toml` and `glossary.toml` and ranks in `Query.guideSearch`): the index
 * entries, `Query.guideStartPage(id)`, `Query.guideTerm(id)` and a search that matches the words
 * of a query in the titles and prose of those entries, the fields and the playbook, grouped by
 * kind. The ranking is the server's job (its own tests); here only the grouping is checked.
 */
type Json = Record<string, unknown>;

const IV30 = 'rollup.iv30@v1.iv30';

const prose = (text: string, names: readonly string[] = []): Json => {
  const at = names.map((n) => text.indexOf(n)).find((i) => i >= 0);
  const name = names.find((n) => text.indexOf(n) === at);
  if (at === undefined || at < 0 || !name) return { segments: [{ text, field: null }] };
  return {
    segments: [
      ...(at > 0 ? [{ text: text.slice(0, at), field: null }] : []),
      { text: name, field: name },
      ...(text.length > at + name.length
        ? [{ text: text.slice(at + name.length), field: null }]
        : []),
    ],
  };
};

export const START_PAGES = [
  {
    id: 'how_the_app_thinks',
    order: 1,
    title: 'How the app thinks about a day',
    summary: 'Every page reads one session; what is not stored for it is UNKNOWN.',
    sections: [
      { title: 'One session', body: 'A page reads one trading day and says which.' },
      { title: 'Unknown is not zero', body: 'A missing value is shown as UNKNOWN with a reason.' },
    ],
    links: [
      { kind: 'term', id: 'session', title: 'Session' },
      { kind: 'term', id: 'unknown', title: 'UNKNOWN' },
    ],
  },
  {
    id: 'read_a_result',
    order: 2,
    title: 'Read a screen result',
    summary: 'What a hit, a near miss and a reject mean.',
    sections: [{ title: 'A hit', body: `It passed every hard rule; ${IV30} is one it may read.` }],
    links: [{ kind: 'playbook', id: 'vrp_scanner', title: 'VRP scanner' }],
  },
];

export const TERMS = [
  {
    id: 'unknown',
    term: 'UNKNOWN',
    short: 'A value the app does not have for the session.',
    body: 'It is never filled in from an earlier day.',
    seeAlso: ['session'],
  },
  {
    id: 'session',
    term: 'Session',
    short: 'The trading day a page is reading.',
    body: 'Every daily value on the page is the one stored for that day.',
    seeAlso: ['unknown'],
  },
  {
    id: 'not_run',
    term: 'NOT_RUN',
    short: 'No run exists for the session being read.',
    body: 'A screener that has not run has no hits, not zero hits.',
    seeAlso: [],
  },
];

/** The `GuideIndex` parts for Start here and the glossary. */
export const START_INDEX = {
  sections: [
    {
      id: 'start',
      title: 'Start here',
      purpose: 'How the app thinks, in the order to read it.',
      entries: START_PAGES.length,
    },
    {
      id: 'glossary',
      title: 'Glossary',
      purpose: 'The app’s own words.',
      entries: TERMS.length,
    },
  ],
  startPages: START_PAGES.map(({ id, order, title, summary }) => ({ id, order, title, summary })),
  terms: TERMS.map(({ id, term, short }) => ({ id, term, short })),
};

/** `Query.guideStartPage(id)`: null for an unknown page. */
export function guideStartPage(id: string): Json {
  const page = START_PAGES.find((p) => p.id === id);
  if (!page) return { data: { guideStartPage: null } };
  return {
    data: {
      guideStartPage: {
        entry: { id: page.id, order: page.order, title: page.title, summary: page.summary },
        sections: page.sections.map((s) => ({ title: s.title, body: prose(s.body, [IV30]) })),
        links: page.links,
      },
    },
  };
}

/** `Query.guideTerm(id)`: null for an unknown term. */
export function guideTerm(id: string): Json {
  const term = TERMS.find((t) => t.id === id);
  if (!term) return { data: { guideTerm: null } };
  const entry = ({ id: tid, term: name, short }: (typeof TERMS)[number]) => ({
    id: tid,
    term: name,
    short,
  });
  return {
    data: {
      guideTerm: {
        entry: entry(term),
        body: prose(term.body),
        seeAlso: term.seeAlso.flatMap((s) => TERMS.filter((t) => t.id === s).map(entry)),
      },
    },
  };
}

interface Entry {
  kind: string;
  id: string;
  title: string;
  text: string;
}

/** Every entry the mocked search can find. */
const ENTRIES: Entry[] = [
  ...START_PAGES.map((p) => ({ kind: 'start', id: p.id, title: p.title, text: p.summary })),
  {
    kind: 'playbook',
    id: 'vrp_scanner',
    title: 'VRP scanner',
    text: 'Finds names whose options price more movement than the shares delivered.',
  },
  {
    kind: 'field',
    id: IV30,
    title: IV30,
    text: 'Our 30-day at-the-money implied volatility.',
  },
  ...TERMS.map((t) => ({ kind: 'term', id: t.id, title: t.term, text: t.short })),
];

const KIND_ORDER = ['start', 'indicator', 'episode', 'playbook', 'field', 'situation', 'term'];

/** `Query.guideSearch(q, limit)`: entries whose title or text holds every word, by kind. */
export function guideSearch(q: string, limit: number): Json {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const found = words.length
    ? ENTRIES.filter((e) => words.every((w) => `${e.title} ${e.text}`.toLowerCase().includes(w)))
    : [];
  const groups = KIND_ORDER.flatMap((kind) => {
    const hits = found
      .filter((e) => e.kind === kind)
      .slice(0, limit)
      .map((e) => ({ kind, id: e.id, title: e.title, snippet: e.text }));
    return hits.length ? [{ kind, hits }] : [];
  });
  return { data: { guideSearch: { query: q, groups } } };
}
