/**
 * The idea model: GET /ideas (one row per ticker, every screener that picked it) turned into
 * what the Ideas page shows: each idea's best pick (decision, score, tier, class), the
 * screeners in the user's priority order with what each one found, and the earnings / expiry
 * context, the screeners' display values and the watch-outs (flags) per idea. Pure; the
 * cached response stays the API's so a priority change can edit it in place.
 */
import type { components } from '@/shared/api';

export type IdeasResponse = components['schemas']['Ideas'];

/** A stored display value: a screener's column (`iv30`, `put_roc`, ...) or a criterion value. */
export type IdeaMetric = number | string;

export interface IdeaPick {
  screenerId: string;
  /** The screener's display name (its id when it has none). */
  screenerName: string;
  user: string;
  version: number | null;
  decision: string;
  score: number | null;
  tier: string | null;
  klass: string | null;
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
  /** Null when the instrument has no ticker (it cannot be opened in Explore). */
  symbol: string | null;
  rank: number;
  /** Every screener that picked the ticker, in the user's priority order. */
  picks: IdeaPick[];
  /** The pick with the best decision (ties: the higher-priority screener). */
  best: IdeaPick;
  nextEarningsDate: string | null;
  daysToEarnings: number | null;
  /** Calendar days to the closest listed expiry (null: no chain). */
  closestExpiryDte: number | null;
  /** Earnings fall on or before the closest expiry. */
  earningsBeforeExpiry: boolean;
  /**
   * The display values by name, from the best pick that has one (a screener's columns, then
   * its criterion values): `iv30`, `hv30`, `iv_hv_ratio`, `put_strike`, ... Only what some
   * screener stored.
   */
  metrics: Record<string, IdeaMetric>;
  /** Flags, liquidity risk and earnings before expiry, each once. */
  watchOut: WatchOut[];
}

export interface ScreenerSummary {
  id: string;
  /** Display name: the config's `name`, else its id. */
  name: string;
  user: string;
  version: number | null;
  /** How many tickers this screener qualified. */
  qualified: number;
  /** The highest-scoring tickers it picked. */
  top: { symbol: string; score: number | null }[];
}

export interface IdeasData {
  session: string;
  total: number;
  ideas: Idea[];
  /** The user's screeners, highest priority first (priority list, then any other picker). */
  screeners: ScreenerSummary[];
}

const DECISION_ORDER = ['QUALIFIED', 'WATCH', 'EVENT_RISK'];
const TOP_PER_SCREENER = 3;

const decisionRank = (decision: string): number => {
  const index = DECISION_ORDER.indexOf(decision);
  return index < 0 ? DECISION_ORDER.length : index;
};

/** "EVENT_RISK" -> "Event risk". */
export function decisionLabel(decision: string): string {
  const text = decision.toLowerCase().replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type DecisionTone = 'positive' | 'accent' | 'warning' | 'neutral';

export function decisionTone(decision: string): DecisionTone {
  if (decision === 'QUALIFIED') return 'positive';
  if (decision === 'WATCH') return 'accent';
  if (decision === 'EVENT_RISK') return 'warning';
  return 'neutral';
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

function toWatchOut(picks: readonly IdeaPick[], earningsBeforeExpiry: boolean): WatchOut[] {
  const ids = picks.flatMap((p) => [
    ...p.flags,
    ...(p.decision === 'LIQUIDITY_RISK' ? ['liquidity_risk'] : []),
  ]);
  if (earningsBeforeExpiry) ids.push('earnings_before_expiry');
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

function toPick(
  pick: components['schemas']['IdeaPick'],
  names: ReadonlyMap<string, string>,
): IdeaPick {
  return {
    screenerId: pick.config_id,
    screenerName: names.get(pick.config_id) ?? pick.config_id,
    flags: pick.flags,
    columns: pick.columns,
    criterionValues: pick.criterion_values,
    user: pick.user,
    version: pick.config_version,
    decision: pick.decision,
    score: pick.score,
    tier: pick.tier,
    klass: pick.klass,
    reasons: pick.reasons,
  };
}

function toIdea(
  item: components['schemas']['Idea'],
  priority: readonly string[],
  names: ReadonlyMap<string, string>,
): Idea | null {
  const order = (id: string) => {
    const index = priority.indexOf(id);
    return index < 0 ? priority.length : index;
  };
  const picks = item.picks
    .map((p) => toPick(p, names))
    .sort((a, b) => order(a.screenerId) - order(b.screenerId));
  const strongest = [...picks].sort((a, b) => decisionRank(a.decision) - decisionRank(b.decision));
  const best = strongest[0];
  if (!best) return null;
  const earningsBeforeExpiry = item.earnings_before_expiry === true;
  return {
    instrumentId: item.instrument_id,
    symbol: item.symbol,
    rank: item.rank,
    picks,
    best,
    nextEarningsDate: item.next_earnings_date,
    daysToEarnings: item.days_to_earnings,
    closestExpiryDte: item.closest_expiry_dte,
    earningsBeforeExpiry,
    metrics: toMetrics(strongest),
    watchOut: toWatchOut(picks, earningsBeforeExpiry),
  };
}

function summarise(
  id: string,
  ideas: readonly Idea[],
  info: components['schemas']['IdeaScreener'] | undefined,
): ScreenerSummary {
  const mine = ideas.flatMap((idea) =>
    idea.picks.filter((p) => p.screenerId === id).map((pick) => ({ idea, pick })),
  );
  const first = mine[0]?.pick;
  return {
    id,
    name: info?.name ?? id,
    user: first?.user ?? info?.user ?? '',
    version: first?.version ?? info?.version ?? null,
    qualified: mine.filter(({ pick }) => pick.decision === 'QUALIFIED').length,
    top: mine
      .filter(({ pick }) => pick.score !== null)
      .sort((a, b) => (b.pick.score ?? 0) - (a.pick.score ?? 0))
      .slice(0, TOP_PER_SCREENER)
      .map(({ idea, pick }) => ({ symbol: idea.symbol ?? idea.instrumentId, score: pick.score })),
  };
}

export function toIdeasData(response: IdeasResponse): IdeasData {
  const info = new Map(response.screeners.map((s) => [s.config_id, s]));
  const names = new Map(response.screeners.map((s) => [s.config_id, s.name]));
  const ideas = response.items
    .map((item) => toIdea(item, response.priority, names))
    .filter((idea): idea is Idea => idea !== null);
  const others = [...new Set(ideas.flatMap((i) => i.picks.map((p) => p.screenerId)))]
    .filter((id) => !response.priority.includes(id))
    .sort();
  return {
    session: response.session,
    total: response.total,
    ideas,
    screeners: [...response.priority, ...others].map((id) => summarise(id, ideas, info.get(id))),
  };
}
