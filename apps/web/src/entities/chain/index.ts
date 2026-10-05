/** Entity: an underlying's option chain (expiries, quotes, Greeks) and its display rows. */
export { useOptionChain, useOptionQuotes } from './api/hooks';
export {
  CHAIN_FACTS,
  CHAIN_FEATURES,
  chainFacts,
  chainRows,
  defaultExpiry,
  DELTA_BAND,
  expiryLabel,
  inDeltaBand,
  NEAR_MONEY,
  plainEnglish,
  upcomingExpiries,
  type ChainFacts,
  type ChainRow,
  type OptionChain,
  type OptionExpiry,
  type OptionQuote,
  type OptionRight,
} from './model/chain';
