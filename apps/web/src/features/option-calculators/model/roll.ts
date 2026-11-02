/**
 * The roll calculator's words from the server's figures: the sentence about buying the sold
 * contract back, and the rolls shown before "See all". Figures are formatted, never derived: the
 * wording follows the sign of what the server sent.
 */
import { formatValue } from '@algotrade/ui';

import type { components } from '@/shared/api';

export type RollPreview = components['schemas']['RollPreview'];
export type RollRow = components['schemas']['RollRow'];
export type OptionGap = components['schemas']['OptionGap'];

/** Rolls shown before "See all". */
export const VISIBLE_ROLLS = 4;

const usd = (value: number) => formatValue(value, { kind: 'currency' }).text;
const pct = (value: number) => formatValue(Math.abs(value), { kind: 'percent', digits: 1 }).text;

/** What buying the sold contract back costs now, and where the shares stand against its strike. */
export function rollSentence(symbol: string, preview: RollPreview): string {
  const cost = `Buying it back now costs ${usd(preview.buy_back)} (middle price)`;
  const over = preview.over_collected;
  const against =
    over === null || over === 0
      ? ''
      : over > 0
        ? `: ${usd(over)} a share more than you collected`
        : `: ${usd(-over)} a share less than you collected`;
  const where = preview.above_strike < 0 ? 'below' : 'above';
  const days = preview.days_left === 1 ? '1 day' : `${String(preview.days_left)} days`;
  return `${cost}${against}. ${symbol} is ${pct(preview.above_strike)} ${where} your strike, with ${days} left.`;
}

/** The rolls to show: the first few, or all of them. */
export function shownRolls(rolls: readonly RollRow[], all: boolean): readonly RollRow[] {
  return all ? rolls : rolls.slice(0, VISIBLE_ROLLS);
}
