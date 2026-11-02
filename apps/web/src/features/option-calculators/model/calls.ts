/**
 * The calls calculator's words from the server's figures: where the shares closed against the
 * trader's price, the dividend's dates, and how many contracts the shares make. Formatted, never derived.
 */
import { formatValue } from '@algotrade/ui';

import type { components } from '@/shared/api';

export type CallsPreview = components['schemas']['CallsPreview'];
export type CallRow = components['schemas']['CallRow'];
export type Dividend = components['schemas']['Dividend'];

const usd = (value: number) => formatValue(value, { kind: 'currency' }).text;
const day = (value: string) => formatValue(value, { kind: 'date', style: 'short' }).text;

/** `ORBT closed at $84.20, 3.1% above your price.` */
export function closedSentence(symbol: string, preview: CallsPreview): string {
  const share = formatValue(Math.abs(preview.above_price), { kind: 'percent', digits: 1 }).text;
  const where = preview.above_price < 0 ? 'below' : 'above';
  return `${symbol} closed at ${usd(preview.priced_at)}, ${share} ${where} your price.`;
}

/** The next ex-dividend date, its amount and the day to own the shares by. */
export interface DividendLine {
  exDate: string;
  amount: string;
  ownBy: string;
}

export function dividendLine(dividend: Dividend): DividendLine {
  return {
    exDate: day(dividend.ex_date),
    amount: formatValue(dividend.amount, { kind: 'currency' }).text,
    ownBy: day(dividend.own_by),
  };
}

/** The contracts the shares make: `3 contracts`. */
export function contractsText(contracts: number): string {
  return contracts === 1 ? '1 contract' : `${String(contracts)} contracts`;
}
