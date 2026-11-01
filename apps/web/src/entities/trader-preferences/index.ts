/**
 * Entity: the trader's stored choices (ADR 0083, amendment 2026-11-01): `useTraderPreferences`
 * is the default Ideas tab (null until the sign-up question is answered) and the watchlist
 * (instrument ids only); `useSaveIdeasTab` and `useSaveWatchlist` change them.
 */
export {
  ensureTraderPreferences,
  useSaveIdeasTab,
  useSaveWatchlist,
  useTraderPreferences,
  type TraderPreferences,
  type WatchedName,
} from './api/trader-preferences';
export { IDEAS_TABS, isIdeasTab, MAX_WATCHLIST, type IdeasTab } from './model/tabs';
