/**
 * The idea model: GET /ideas (one row per ticker, every screener that picked it) turned into
 * what the Ideas page shows: each idea's best pick (decision, score, tier, class), the
 * screeners in the user's priority order with what each one found, and the earnings / expiry
 * context. Pure; the cached response stays the API's so a priority change can edit it in place.
 */
import type { components } from '@/shared/api';

export type IdeasResponse = components['schemas']['Ideas'];

export interface IdeaPick {
  screenerId: string;
  user: string;
  version: number | null;
  decision: string;
  score: number | null;
  tier: string | null;
  klass: string | null;
  reasons: string;
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
}

export interface ScreenerSummary {
  id: string;
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

function toPick(pick: components['schemas']['IdeaPick']): IdeaPick {
  return {
    screenerId: pick.config_id,
    user: pick.user,
    version: pick.config_version,
    decision: pick.decision,
    score: pick.score,
    tier: pick.tier,
    klass: pick.klass,
    reasons: pick.reasons,
  };
}

function toIdea(item: components['schemas']['Idea'], priority: readonly string[]): Idea | null {
  const order = (id: string) => {
    const index = priority.indexOf(id);
    return index < 0 ? priority.length : index;
  };
  const picks = item.picks.map(toPick).sort((a, b) => order(a.screenerId) - order(b.screenerId));
  const best = [...picks].sort((a, b) => decisionRank(a.decision) - decisionRank(b.decision))[0];
  if (!best) return null;
  return {
    instrumentId: item.instrument_id,
    symbol: item.symbol,
    rank: item.rank,
    picks,
    best,
    nextEarningsDate: item.next_earnings_date,
    daysToEarnings: item.days_to_earnings,
    closestExpiryDte: item.closest_expiry_dte,
    earningsBeforeExpiry: item.earnings_before_expiry === true,
  };
}

function summarise(id: string, ideas: readonly Idea[]): ScreenerSummary {
  const mine = ideas.flatMap((idea) =>
    idea.picks.filter((p) => p.screenerId === id).map((pick) => ({ idea, pick })),
  );
  const first = mine[0]?.pick;
  return {
    id,
    user: first?.user ?? '',
    version: first?.version ?? null,
    qualified: mine.filter(({ pick }) => pick.decision === 'QUALIFIED').length,
    top: mine
      .filter(({ pick }) => pick.score !== null)
      .sort((a, b) => (b.pick.score ?? 0) - (a.pick.score ?? 0))
      .slice(0, TOP_PER_SCREENER)
      .map(({ idea, pick }) => ({ symbol: idea.symbol ?? idea.instrumentId, score: pick.score })),
  };
}

export function toIdeasData(response: IdeasResponse): IdeasData {
  const ideas = response.items
    .map((item) => toIdea(item, response.priority))
    .filter((idea): idea is Idea => idea !== null);
  const others = [...new Set(ideas.flatMap((i) => i.picks.map((p) => p.screenerId)))]
    .filter((id) => !response.priority.includes(id))
    .sort();
  return {
    session: response.session,
    total: response.total,
    ideas,
    screeners: [...response.priority, ...others].map((id) => summarise(id, ideas)),
  };
}
