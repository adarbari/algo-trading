/**
 * The setup-ideas model: the `SetupIdeas` response as the page shows it. Pure: it renames served
 * values (the server decided the setups, the order and the cap) and attaches each idea to its
 * group by the server's `setupId`; it never ranks, filters or counts (docs/api/read-model.md
 * "Presentation is not derivation").
 */
import type { ServedUnknown } from '@/entities/availability';
import type { gqlTypes } from '@/shared/api';

export type SetupIdeasResponse = gqlTypes.SetupIdeasQuery;
type Served = NonNullable<SetupIdeasResponse['setupIdeas']>;

export interface SetupGroup {
  edgeId: string;
  name: string;
  /** The stored verdict level: `works` or `promising`. */
  level: string;
  /** The out-of-sample lift in points (backtested, hypothetical); null: not measured. */
  liftPts: number | null;
  oosTrades: number | null;
  basisHorizon: number | null;
  /** The screener the verdict rests on (the page opens a ticker with it). */
  basisScreener: string;
  /** `picked`, `nothing_picked`, `not_a_decision_day` or `unknown` (with `unknown`). */
  state: string;
  unknown: ServedUnknown | null;
  picked: number;
  /** The ideas under the cap that rank under this setup. */
  shown: number;
  ideas: SetupIdea[];
}

export interface SetupIdea {
  rank: number;
  instrumentId: string;
  symbol: string | null;
  name: string | null;
  setupId: string;
  /** Its place among the setup's own picks. */
  place: number;
  alsoIn: { edgeId: string; edgeName: string; place: number }[];
  watchOut: string[];
  metrics: { name: string; value: number | string }[];
  regime: string | null;
}

export interface SetupIdeas {
  session: string;
  /** `listed`: a setup qualifies; `unproven`: none does. */
  state: 'listed' | 'unproven';
  total: number;
  leftOut: { kind: string; count: number }[];
  groups: SetupGroup[];
  /** Every idea, best first (the same rows the groups hold). */
  ideas: SetupIdea[];
}

function idea(i: Served['ideas'][number]): SetupIdea {
  return {
    rank: i.rank,
    instrumentId: i.instrumentId,
    symbol: i.instrument?.symbol ?? null,
    name: i.instrument?.name ?? null,
    setupId: i.setupId,
    place: i.place,
    alsoIn: i.alsoIn,
    watchOut: i.watchOut,
    metrics: i.metrics.flatMap((m) =>
      typeof m.value === 'number' || typeof m.value === 'string'
        ? [{ name: m.name, value: m.value }]
        : [],
    ),
    regime: i.result?.regime ?? null,
  };
}

export function toSetupIdeas(response: SetupIdeasResponse): SetupIdeas | null {
  const found = response.setupIdeas;
  if (!found) return null;
  const ideas = found.ideas.map(idea);
  return {
    session: found.session,
    state: found.state === 'listed' ? 'listed' : 'unproven',
    total: found.total,
    leftOut: found.leftOut,
    ideas,
    groups: found.groups.map((g) => ({
      edgeId: g.edgeId,
      name: g.name,
      level: g.level,
      liftPts: g.liftPts ?? null,
      oosTrades: g.oosTrades ?? null,
      basisHorizon: g.basisHorizon ?? null,
      basisScreener: g.basisScreener,
      state: g.state,
      unknown: g.unknown ?? null,
      picked: g.picked,
      shown: g.shown,
      ideas: ideas.filter((i) => i.setupId === g.edgeId),
    })),
  };
}
