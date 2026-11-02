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
  /** The setup's state at the session (On or Paused for a listed setup; null: not served). */
  setupState: { state: string; reason: string } | null;
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
  /** The Premium tab's option row (null on Stocks). */
  option: PremiumOption | null;
}

/** One leg of a Premium idea's example position (the server's figures, per share). */
export interface PremiumLeg {
  right: string;
  strike: number;
  expiry: string;
  /** Signed: negative is sold. */
  qty: number;
  mid: number;
}

/** A Premium idea's option row: the example position its setup would open tonight. */
export interface PremiumOption {
  legs: PremiumLeg[];
  expiry: string | null;
  /** Per contract, positive when received. */
  credit: number | null;
  /** Per contract. */
  collateral: number | null;
  returnOnCollateral: number | null;
  /** The model chance at least one sold leg finishes in the money, 0 to 1. */
  assignmentChance: number | null;
  /** Why there is no example (every figure null). */
  unknown: ServedUnknown | null;
  chanceUnknown: ServedUnknown | null;
  collateralUnknown: ServedUnknown | null;
}

export interface SetupIdeas {
  session: string;
  /** `listed`: a setup qualifies; `unproven`: none does. */
  state: 'listed' | 'unproven';
  total: number;
  /** The ideas under the cap before the viewer's watchlist kept the watched ones (null: none). */
  watchlist: number | null;
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
    option: i.option
      ? {
          legs: i.option.legs,
          expiry: i.option.expiry ?? null,
          credit: i.option.credit ?? null,
          collateral: i.option.collateral ?? null,
          returnOnCollateral: i.option.returnOnCollateral ?? null,
          assignmentChance: i.option.assignmentChance ?? null,
          unknown: i.option.unknown ?? null,
          chanceUnknown: i.option.chanceUnknown ?? null,
          collateralUnknown: i.option.collateralUnknown ?? null,
        }
      : null,
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
    watchlist: found.watchlist ?? null,
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
      setupState: g.setupState ?? null,
      picked: g.picked,
      shown: g.shown,
      ideas: ideas.filter((i) => i.setupId === g.edgeId),
    })),
  };
}
