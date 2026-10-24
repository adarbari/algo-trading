/**
 * The idea model: the `IdeasPage` response (one row per ticker, ranked on the server by the Ideas
 * rule and served from its best pick) turned into what the Ideas page shows: each idea's best
 * pick (decision, reasons, criteria outcomes), the screeners that picked it, its facts by
 * catalogue name (earnings, nearest expiry, IV: the server's values for the session or why not),
 * the best pick's stored display values and watch-outs; and the screeners with their run, picked
 * count and first picks, all counted by the server over the whole run. Pure: it renames served
 * values, it never chooses among picks or computes one (docs/api/read-model.md "Presentation is
 * not derivation").
 */
import type { ServedUnknown } from '@/entities/availability';
import type { ServedValue } from '@/entities/feature';
import type { FilterFacets } from '@/entities/filter';
import type { gqlTypes } from '@/shared/api';

import { IDEA_FACTS } from './facts';

export type IdeasResponse = gqlTypes.IdeasPageQuery;
type ServedIdeas = NonNullable<IdeasResponse['ideas']>;
type ServedItem = ServedIdeas['items'][number];
type ServedScreener = ServedIdeas['screeners'][number];
type ServedPaused = ServedIdeas['paused'][number];

/** A stored display value: a screener's column (`hv30`, `put_roc`, ...) or a criterion value. */
export type IdeaMetric = number | string;

/** The best pick of an idea: what its screener decided and why. */
export interface IdeaPick {
  screenerId: string;
  /** The screener's display name (its id when it has none). */
  screenerName: string;
  decision: string;
  /** The screener's own score for the ticker (not the idea's score). */
  score: number | null;
  reasons: string;
  /** Each criterion's served outcome (`PASS`, `NEAR`, `FAIL`, `MISSING`), in the screener's order. */
  criteria: { id: string; outcome: string }[];
}

/** One screener that picked an idea: its place in the screener's run and what it earns. */
export interface PickedBy {
  screenerId: string;
  screenerName: string;
  /** The viewer's own screener (not a site preset). */
  own: boolean;
  position: number;
  /** Weight over position, as the Ideas rule scores it. */
  score: number;
  decision: string;
}

/** One reason to look twice at an idea (a flag, a liquidity-risk pick, earnings before expiry). */
export interface WatchOut {
  id: string;
  label: string;
}

export interface Idea {
  instrumentId: string;
  /** Null when the session's reference snapshot does not have the instrument. */
  symbol: string | null;
  /** The company or fund name (null when the reference snapshot does not have the instrument). */
  name: string | null;
  rank: number;
  /** The idea's score under the Ideas rule: its best pick's weight over position. */
  score: number;
  /** The pick the idea is served from (the server's best pick). */
  best: IdeaPick;
  /** Every screener that picked the ticker, the best first (the server's order). */
  pickedBy: PickedBy[];
  /** The regime label and size its best pick was stamped with (null: not stamped). */
  regime: string | null;
  sizeMultiplier: number | null;
  /** The served facts (`IDEA_FEATURES`) by catalogue name: a value, or why it is UNKNOWN. */
  facts: Readonly<Record<string, ServedValue>>;
  /** The best pick's display values by name: `hv30`, `iv_hv_ratio`, `put_strike`, ... */
  metrics: Record<string, IdeaMetric>;
  /** Flags, liquidity risk and earnings before expiry of the best pick, each once. */
  watchOut: WatchOut[];
}

/** A pick the regime gate held back: not an idea, listed apart with its reason. */
export interface PausedIdea {
  instrumentId: string;
  /** Null when the session's reference snapshot does not have the instrument. */
  symbol: string | null;
  screenerId: string;
  screenerName: string;
  score: number | null;
  /** Why it is paused (the label and the rule), as the run stored it. */
  reason: string;
  regime: string | null;
}

export interface ScreenerSummary {
  id: string;
  /** Display name: the config's `name`, else its id. */
  name: string;
  /** Whose runs are its: the user's id, or `site` for a preset. */
  owner: string;
  version: number | null;
  /** How many tickers its run for the session picked (over the whole run). */
  picked: number;
  /** Why the screener has no run for the session (ADR 0056), else null. */
  notRun: ServedUnknown | null;
  /** The run's order follows values the viewer's licences do not cover: it adds no idea. */
  withheld: boolean;
  /** The run record's own coverage (`COMPLETE`, `PARTIAL`), null: no run or not recorded. */
  coverage: string | null;
  /** What the run went without, in the server's public words (never a table or step name). */
  gaps: { kind: string; kindText: string; guideTerm: string }[];
  /** Its first picks that count towards the ideas, best first. */
  top: { symbol: string; score: number | null }[];
}

export interface IdeasData {
  /** The session every value is for; null: nothing stored yet. */
  session: string | null;
  total: number;
  ideas: Idea[];
  /** Whether the server has more ideas after the ones loaded (the next page's cursor exists). */
  hasMore: boolean;
  /** How many picks the gate paused over every run, and the first of them (never hidden). */
  pausedTotal: number;
  paused: PausedIdea[];
  /** The viewer's screeners (their own first, then the site presets by id). */
  screeners: ScreenerSummary[];
  /** The server's counts for the filters in force (null: none sent or nothing stored). */
  facets: FilterFacets | null;
}

const FLAG_LABELS: Record<string, string> = {
  leveraged_inverse: 'Leveraged / inverse',
  large_move: 'Large move',
  liquidity_risk: 'Liquidity risk',
  earnings_before_expiry: 'Earnings before expiry',
};

/** "large_move" -> "Large move" (flags a screener names itself). */
function flagLabel(id: string): string {
  const known = FLAG_LABELS[id];
  if (known) return known;
  const text = id.toLowerCase().replace(/[_-]+/g, ' ').trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The served value of `name` for an idea (undefined: not asked for). */
export function factOf(idea: Idea, name: string): ServedValue | undefined {
  return idea.facts[name];
}

/** True when the server says the earnings fall on or before the nearest expiry. */
export function earningsBeforeExpiry(idea: Idea): boolean {
  return factOf(idea, IDEA_FACTS.earningsBeforeExpiry)?.value === true;
}

function toIdea(item: ServedItem, names: ReadonlyMap<string, string>): Idea {
  const nameOf = (id: string): string => names.get(id) ?? id;
  const served = item.instrument?.features ?? [];
  return {
    instrumentId: item.instrumentId,
    symbol: item.instrument?.symbol ?? null,
    name: item.instrument?.name ?? null,
    rank: item.rank,
    score: item.score,
    best: {
      screenerId: item.best.configId,
      screenerName: nameOf(item.best.configId),
      decision: item.best.decision,
      score: item.best.score ?? null,
      reasons: item.best.reasons,
      criteria: item.best.criteria,
    },
    pickedBy: item.pickedBy.map((p) => ({
      screenerId: p.configId,
      screenerName: nameOf(p.configId),
      own: p.own,
      position: p.position,
      score: p.score,
      decision: p.decision,
    })),
    regime: item.regime ?? null,
    sizeMultiplier: item.sizeMultiplier ?? null,
    facts: Object.fromEntries(served.map((v) => [v.name, v as ServedValue])),
    metrics: Object.fromEntries(item.metrics.map((m) => [m.name, m.value as IdeaMetric])),
    watchOut: item.watchOut.map((id) => ({ id, label: flagLabel(id) })),
  };
}

function toScreener(entry: ServedScreener): ScreenerSummary {
  return {
    id: entry.screener.id,
    name: entry.screener.name,
    owner: entry.screener.owner,
    version: entry.run?.configVersion ?? entry.screener.version ?? null,
    picked: entry.picked,
    notRun: entry.notRun ?? null,
    withheld: entry.withheld,
    coverage: entry.run?.coverage ?? null,
    gaps: (entry.run?.unavailable ?? []).map((u) => ({
      kind: u.kind,
      kindText: u.kindText,
      guideTerm: u.guideTerm,
    })),
    top: entry.top.map((t) => ({
      symbol: t.instrument?.symbol ?? t.instrumentId,
      score: t.score ?? null,
    })),
  };
}

export const NO_IDEAS: IdeasData = {
  session: null,
  total: 0,
  ideas: [],
  hasMore: false,
  pausedTotal: 0,
  paused: [],
  screeners: [],
  facets: null,
};

function toPaused(entry: ServedPaused, names: ReadonlyMap<string, string>): PausedIdea {
  return {
    instrumentId: entry.instrumentId,
    symbol: entry.instrument?.symbol ?? null,
    screenerId: entry.result.configId,
    screenerName: names.get(entry.result.configId) ?? entry.result.configId,
    score: entry.result.score ?? null,
    reason: entry.result.reasons,
    regime: entry.result.regime ?? null,
  };
}

export function toIdeasData(response: IdeasResponse): IdeasData {
  const found = response.ideas;
  if (!found) return NO_IDEAS;
  const names = new Map(found.screeners.map((s) => [s.screener.id, s.screener.name]));
  return {
    session: found.session,
    total: found.total,
    ideas: found.items.map((item) => toIdea(item, names)),
    hasMore: found.hasMore,
    pausedTotal: found.pausedTotal,
    paused: found.paused.map((entry) => toPaused(entry, names)),
    screeners: found.screeners.map(toScreener),
    facets: found.facets ?? null,
  };
}
