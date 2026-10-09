/** The facts the Ideas page shows per idea, asked by catalogue name (ADR 0038). */
import { feature } from '@/shared/api';

/** The facts each idea is shown with, asked by catalogue name for the ideas' session. */
export const IDEA_FACTS = {
  nextEarnings: feature('rollup.earnings@v1.next_earnings_date'),
  lastEarnings: feature('rollup.earnings@v1.last_earnings_date'),
  /** Counted in sessions, not calendar days. */
  sessionsToEarnings: feature('rollup.earnings@v1.days_to_earnings'),
  /** Calendar days to the nearest listed expiry. */
  expiryDte: feature('rollup.nearest_expiry@v1.dte'),
  earningsBeforeExpiry: feature('feature.earnings_before_expiry'),
  iv30: feature('feature.vrp_iv30'),
  /** The session's close and the 1-session return, shown beside the ticker. */
  close: feature('rollup.price_stats@v2.close'),
  ret1d: feature('rollup.trend_stats@v2.ret_1d'),
  /** The ticker of the sector ETF the company's sector maps to (the sector line under the name). */
  sectorEtf: feature('rollup.relative_strength@v1.sector_etf'),
} as const;

export const IDEA_FEATURES = Object.values(IDEA_FACTS);
