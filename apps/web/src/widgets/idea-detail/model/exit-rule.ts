/**
 * The exit rule as one line of text for "Copy exit rule as text": the served stop and hold in
 * words, labelled backtested (hypothetical). Only served figures are formatted; nothing is
 * derived (an ATR stop is its multiple and its ATR, never their product; a price is the served
 * price). A share setup's take profit is a rise of the entry close, its target.
 */
import { formatValue } from '@algotrade/ui';

import type { IdeaDetail } from '@/entities/idea';

const money = (value: number) => formatValue(value, { kind: 'currency' }).text;

export function exitRuleText(
  exit: IdeaDetail['exitRule'],
  prices?: IdeaDetail['exitPrices'],
): string | null {
  const parts: string[] = [];
  const stop = exit.stop;
  const at = prices?.stop == null ? '' : ` (${money(prices.stop)})`;
  if (stop && stop.fraction !== null && stop.basis === 'CREDIT') {
    const times = formatValue(stop.fraction, { kind: 'number', digits: 1 }).text;
    parts.push(`declared stop ${times} × the credit`);
  } else if (stop && stop.fraction !== null && stop.basis === 'COLLATERAL') {
    const share = formatValue(stop.fraction, { kind: 'percent', digits: 1 }).text;
    parts.push(`stop ${share} of the collateral`);
  } else if (stop && stop.fraction !== null) {
    const declared = stop.kind === 'DECLARED' ? 'declared ' : '';
    const pct = formatValue(stop.fraction, { kind: 'percent', digits: 1 }).text;
    parts.push(`${declared}stop ${pct} below the entry close${at}`);
  } else if (stop && stop.multiple !== null) {
    const times = formatValue(stop.multiple, { kind: 'number', digits: 1 }).text;
    parts.push(`stop ${times} × ATR(14)${at}`);
  }
  if (exit.takeProfit != null && exit.takeProfitBasis === 'ENTRY') {
    const at = prices?.target == null ? '' : ` (${money(prices.target)})`;
    parts.push(
      `target ${formatValue(exit.takeProfit, { kind: 'percent', digits: 1 }).text} above the entry close${at}`,
    );
  }
  if (exit.holdSessions !== null) {
    parts.push(`hold ${String(exit.holdSessions)} sessions`);
  }
  return parts.length === 0
    ? null
    : `Historical exit rule: ${parts.join('; ')}. Backtested (hypothetical).`;
}
