/**
 * The Guide's playbook and situation reads for the end-to-end tests (a mock of what the
 * server derives, docs/ui/guide.md section 3): the index's families and situations,
 * `Query.guidePlaybook` and `Query.guideSituation` for a breakout and a VRP playbook and one
 * situation, and the linked prose (text cut at the catalogue names it mentions, as the
 * server does).
 */
type Json = Record<string, unknown>;

/** Text cut at the first mention of each name: `{ text, field }` segments, as `GuideProse`. */
export function linked(text: string, names: readonly string[]): Json {
  const segments: Json[] = [];
  let rest = text;
  for (;;) {
    const hits = names
      .map((name) => ({ name, at: rest.indexOf(name) }))
      .filter((hit) => hit.at >= 0)
      .sort((a, b) => a.at - b.at);
    const hit = hits[0];
    if (!hit) break;
    if (hit.at > 0) segments.push({ text: rest.slice(0, hit.at), field: null });
    segments.push({ text: hit.name, field: hit.name });
    rest = rest.slice(hit.at + hit.name.length);
  }
  if (rest) segments.push({ text: rest, field: null });
  return { text, segments };
}

const IV30 = 'rollup.iv30@v1.iv30';
const IV_HV = 'feature.iv_hv_ratio';
const HV30 = 'rollup.price_stats@v2.hv30';

export const SITUATION = {
  slug: 'earnings-gap-inside-the-window',
  name: 'Earnings gap inside the window',
  signs: 'A report in the next 30 days lifts the reading.',
  do: 'Screens flag it; read rollup.iv30@v1.iv30 beside the earnings date.',
  affects: [IV30],
};

export const FAMILIES = [
  { id: 'breakouts', title: 'Breakouts', playbooks: [{ id: 'breakout', name: 'Breakout' }] },
  { id: 'income', title: 'Option income', playbooks: [{ id: 'vrp_scanner', name: 'VRP scanner' }] },
];

const PLAYBOOKS: Record<string, Json> = {
  breakout: {
    id: 'breakout',
    name: 'Breakout',
    family: 'breakouts',
    familyTitle: 'Breakouts',
    version: 1,
    prose: {
      summary: linked('Finds shares that closed above their highest price of the last month.', []),
      hit: linked('A close above the prior 20-session high on more volume than normal.', []),
      notChecked: linked('Whether the break holds, earnings or news, or the regime.', []),
      beforeActing: [
        linked(
          'A breakout on low volume fails most; this screen asks for volume above normal.',
          [],
        ),
      ],
      sources: ['O’Neil, How to Make Money in Stocks'],
    },
    criteria: [
      {
        name: 'breakout_20d',
        asks: 'Closed above the 20-session high',
        field: HV30,
        rule: 'gt 0',
        mode: 'hard',
        onMiss: null,
      },
    ],
    tieBreak: HV30,
    tieBreakDescending: true,
    related: [{ id: 'vrp_scanner', name: 'VRP scanner', reason: 'the option-income side' }],
    situations: [],
  },
  vrp_scanner: {
    id: 'vrp_scanner',
    name: 'VRP scanner',
    family: 'income',
    familyTitle: 'Option income',
    version: 1,
    prose: {
      summary: linked('Finds names whose options price more movement than the stock delivers.', []),
      hit: linked('Implied volatility well above realised, in a liquid name.', []),
      notChecked: linked('Whether a report or event lies inside the option’s life.', []),
      beforeActing: [
        linked(`Earnings inside the 30 days lift ${IV30} without the stock being rich.`, [IV30]),
      ],
      sources: [],
    },
    criteria: [
      {
        name: 'iv_rich',
        asks: 'Implied volatility is rich',
        field: IV30,
        rule: 'gte 0.4 soft tolerance 0.05',
        mode: 'soft',
        onMiss: 'WATCH',
      },
      {
        name: 'iv_over_hv',
        asks: 'Options price more than the stock delivered',
        field: IV_HV,
        rule: 'gt 1.25',
        mode: 'hard',
        onMiss: null,
      },
    ],
    tieBreak: IV_HV,
    tieBreakDescending: true,
    related: [{ id: 'breakout', name: 'Breakout', reason: 'the chart side' }],
    situations: [{ slug: SITUATION.slug, name: SITUATION.name, fields: [IV30] }],
  },
};

/** `Query.guidePlaybook(id)`: null for an id that is not a site playbook. */
export function guidePlaybook(id: string): Json {
  return { data: { guidePlaybook: PLAYBOOKS[id] ?? null } };
}

/** `Query.guideSituation(slug)`: the one situation, with the playbooks reading its fields. */
export function guideSituation(slug: string): Json {
  if (slug !== SITUATION.slug) return { data: { guideSituation: null } };
  return {
    data: {
      guideSituation: {
        slug: SITUATION.slug,
        name: SITUATION.name,
        signs: linked(SITUATION.signs, []),
        do: linked(SITUATION.do, SITUATION.affects),
        affects: SITUATION.affects,
        playbooks: [{ id: 'vrp_scanner', name: 'VRP scanner', fields: [IV30] }],
      },
    },
  };
}
