/**
 * The evidence an edge's verdict rests on (ADR 0064 / 0065): the types of the served trade ledger
 * (`Query.edgeTrades`, the verdict basis's picks, paged and sorted by the server) and variant grid
 * (`Query.edgeVariants`). A per-name value under a licence the viewer lacks is an `unknown`, never
 * a number; every figure is the read model's. Names only: no derivation here.
 */
import type { gqlTypes } from '@/shared/api';

export type TradePeriod = 'IN_SAMPLE' | 'OUT_OF_SAMPLE' | 'LIVE' | 'ALL';

export type TradeSort =
  | 'DECISION'
  | 'EXIT'
  | 'INSTRUMENT'
  | 'SYMBOL'
  | 'RANK'
  | 'STATUS'
  | 'VALUE'
  | 'SCORE'
  | 'DRAWDOWN'
  | 'ADV';

export interface EvidenceUnknown {
  code: gqlTypes.UnknownCode;
  kind: gqlTypes.UnavailableKind;
  guideTerm: string;
  kindText: string;
}

export interface TradeNumber {
  value: number | null;
  unknown: EvidenceUnknown | null;
}

export interface TradeText {
  value: string | null;
  unknown: EvidenceUnknown | null;
}

export interface TradeFlag {
  value: boolean | null;
  unknown: EvidenceUnknown | null;
}

export interface EdgeTradeRow {
  variant: string;
  horizonSessions: number;
  decisionSession: string;
  entrySession: string | null;
  exitSession: string | null;
  instrumentId: string;
  symbol: TradeText;
  company: TradeText;
  symbolAsOf: string | null;
  rank: number | null;
  status: string;
  excludedReason: string | null;
  hit: boolean | null;
  delisted: boolean;
  beforeSplit: boolean;
  source: string;
  score: TradeNumber;
  value: TradeNumber;
  grossValue: TradeNumber;
  maxDrawdown: number | null;
  advUsd: TradeNumber;
  reference: TradeNumber;
  touch: TradeFlag;
}

export interface EdgeTradePage {
  period: TradePeriod;
  page: number;
  pageSize: number;
  total: number;
  basis: string | null;
  licence: string | null;
  oosHidden: boolean;
  symbolsSnapshot: string | null;
  unknown: EvidenceUnknown | null;
  rows: EdgeTradeRow[];
}

export interface VariantFigures {
  winRate: number | null;
  baseRate: number | null;
  liftPts: number | null;
  decileSpread: number | null;
  trades: number | null;
}

export interface EdgeVariant {
  edgeVariant: string;
  variant: string;
  horizonSessions: number;
  inSample: VariantFigures | null;
  outOfSample: VariantFigures | null;
  all: VariantFigures | null;
  official: boolean;
  notPreChosen: boolean;
  modelFit: boolean;
}

export interface EdgeVariants {
  basis: string | null;
  trials: number | null;
  oosHidden: boolean;
  unknown: EvidenceUnknown | null;
  rows: EdgeVariant[];
}
