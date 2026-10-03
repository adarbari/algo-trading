/** Entity: an underlying's option chain (expiries, quotes, Greeks) and its display rows. */
export { useOptionChain } from './api/hooks';
export {
  chainRows,
  defaultExpiry,
  DELTA_BAND,
  expiryLabel,
  inDeltaBand,
  NEAR_MONEY,
  plainEnglish,
  spotOf,
  type ChainRow,
  type OptionChain,
  type OptionQuote,
  type OptionRight,
} from './model/chain';
