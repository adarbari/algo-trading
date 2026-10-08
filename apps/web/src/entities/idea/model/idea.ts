/**
 * The idea model: the `IdeasPage` response (one row per ticker with every screener that picked
 * it, ranked on the server) turned into what the Ideas page shows: each idea's best pick
 * (decision, score), its facts by catalogue name (earnings, nearest expiry, IV: the server's
 * values for the session or why not), the screeners' stored display values and the watch-outs;
 * and the screeners in priority order with their run, picked count and best picks, all counted
 * by the server over the whole run. Pure: it chooses among served values, it never computes
 * one (docs/api/read-model.md "Presentation is not derivation").
 */
import type { ServedUnknown } from '@/entities/availability';
import type { ServedValue } from '@/entities/feature';
import type { gqlTypes } from '@/shared/api';

import { IDEA_FACTS } from './facts';

export type IdeasResponse = gqlTypes.IdeasPageQuery;
type ServedIdeas = NonNullable<IdeasResponse['ideas']>;
type ServedItem = ServedIdeas['items'][number];
type ServedPick = ServedItem['picks'][number];
type ServedScreener = ServedIdeas['screeners'][number];
type ServedPaused = ServedIdeas['paused'][number];

/** A stored display value: a screener's column (`hv30`, `put_roc`, ...) or a criterion value. */
export type IdeaMetric = number | string;

export interface IdeaPick {
  screenerId: string;
  /** The screener's display name (its id when it has none). */
  screenerName: string;
  decision: string;
  score: number | null;
  reasons: string;
  /** The screener's display columns for the ticker. */
  columns: Record<string, unknown>;
  /** What each criterion was judged on (criterion id -> value). */
  criterionValues: Record<string, unknown>;
  /** The screener's flags that hold for the ticker (ids, e.g. `leveraged_inverse`). */
  flags: string[];
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
  rank: number;
  /** Every screener that picked the ticker, highest priority first (the server's order). */
  picks: IdeaPick[];
  /** The pick with the best decision (ties: the higher-priority screener). */
  best: IdeaPick;
  /** The regime label and size its best-priority pick was stamped with (null: not stamped). */
  regime: string | null;
  sizeMultiplier: number | null;
  /** The served facts (`IDEA_FEATURES`) by catalogue name: a value, or why it is UNKNOWN. */
  facts: Readonly<Record<string, ServedValue>>;
  /**
   * The display values by name, from the best pick that has one (a screener's columns, then
   * its criterion values): `hv30`, `iv_hv_ratio`, `put_strike`, ... Only what some screener
   * stored.
   */
  metrics: Record<string, IdeaMetric>;
  /** Flags, liquidity risk and earnings before expiry, each once. */
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
  /** Why it has no run for the session (null: it ran). */
  /** Why the screener has no run for the session (ADR 0056), else null. */
  notRun: ServedUnknown | null;
  /** Its best picks of the run, by rank. */
  top: { symbol: string; score: number | null }[];
}

export interface IdeasData {
  /** The session every value is for; null: nothing stored yet. */
  session: string | null;
  total: number;
  ideas: Idea[];
  /** How many picks the gate paused over every run, and the first of them (never hidden). */
  pausedTotal: number;
  paused: PausedIdea[];
  /** The user's screeners, highest priority first (priority list, then the rest by id). */
  screeners: ScreenerSummary[];
}

const DECISION_ORDER = ['QUALIFIED', 'WATCH', 'EVENT_RISK'];

const decisionRank = (decision: string): number => {
  const index = DECISION_ORDER.indexOf(decision);
  return index < 0 ? DECISION_ORDER.length : index;
};

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

function toWatchOut(picks: readonly IdeaPick[], beforeExpiry: boolean): WatchOut[] {
  const ids = picks.flatMap((p) => [
    ...p.flags,
    ...(p.decision === 'LIQUIDITY_RISK' ? ['liquidity_risk'] : []),
  ]);
  if (beforeExpiry) ids.push('earnings_before_expiry');
  return [...new Set(ids)].map((id) => ({ id, label: flagLabel(id) }));
}

function toMetrics(picks: readonly IdeaPick[]): Record<string, IdeaMetric> {
  const out: Record<string, IdeaMetric> = {};
  for (const pick of picks) {
    for (const [key, value] of Object.entries({ ...pick.criterionValues, ...pick.columns })) {
      if (!(key in out) && (typeof value === 'number' || typeof value === 'string')) {
        out[key] = value;
      }
    }
  }
  return out;
}

const byName = <T extends { value?: unknown }>(
  entries: readonly T[],
  key: (entry: T) => string,
): Record<string, unknown> => Object.fromEntries(entries.map((e) => [key(e), e.value]));

function toPick(pick: ServedPick, names: ReadonlyMap<string, string>): IdeaPick {
  return {
    screenerId: pick.configId,
    screenerName: names.get(pick.configId) ?? pick.configId,
    decision: pick.decision,
    score: pick.score ?? null,
    reasons: pick.reasons,
    columns: byName(pick.columns, (c) => c.name),
    criterionValues: byName(pick.criteria, (c) => c.id),
    flags: pick.flags,
  };
}

function toIdea(item: ServedItem, names: ReadonlyMap<string, string>): Idea | null {
  const picks = item.picks.map((p) => toPick(p, names));
  const strongest = [...picks].sort((a, b) => decisionRank(a.decision) - decisionRank(b.decision));
  const best = strongest[0];
  if (!best) return null;
  const served = item.instrument?.features ?? [];
  const facts = Object.fromEntries(served.map((v) => [v.name, v as ServedValue]));
  const idea: Idea = {
    instrumentId: item.instrumentId,
    symbol: item.instrument?.symbol ?? null,
    rank: item.rank,
    picks,
    best,
    regime: item.regime ?? null,
    sizeMultiplier: item.sizeMultiplier ?? null,
    facts,
    metrics: toMetrics(strongest),
    watchOut: [],
  };
  return { ...idea, watchOut: toWatchOut(picks, earningsBeforeExpiry(idea)) };
}

function toScreener(entry: ServedScreener): ScreenerSummary {
  return {
    id: entry.screener.id,
    name: entry.screener.name,
    owner: entry.screener.owner,
    version: entry.run?.configVersion ?? entry.screener.version ?? null,
    picked: entry.picked,
    notRun: entry.notRun ?? null,
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
  pausedTotal: 0,
  paused: [],
  screeners: [],
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
    ideas: found.items
      .map((item) => toIdea(item, names))
      .filter((idea): idea is Idea => idea !== null),
    pausedTotal: found.pausedTotal,
    paused: found.paused.map((entry) => toPaused(entry, names)),
    screeners: found.screeners.map(toScreener),
  };
}
