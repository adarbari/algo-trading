/**
 * The exit rule as one line of text for "Copy exit rule as text": the served stop and hold in
 * words, labelled backtested (hypothetical). Only served figures are formatted; nothing is
 * derived (an ATR stop is its multiple and its ATR, never their product).
 */
import { formatValue } from '@algotrade/ui';

import type { IdeaDetail } from '@/entities/idea';

export function exitRuleText(exit: IdeaDetail['exitRule']): string | null {
  const parts: string[] = [];
  const stop = exit.stop;
  if (stop && stop.fraction !== null) {
    parts.push(
      `stop ${formatValue(stop.fraction, { kind: 'percent', digits: 1 }).text} below the entry close`,
    );
  } else if (stop && stop.multiple !== null) {
    parts.push(`stop ${formatValue(stop.multiple, { kind: 'number', digits: 1 }).text} × ATR(14)`);
  }
  if (exit.holdSessions !== null) {
    parts.push(`hold ${String(exit.holdSessions)} sessions`);
  }
  return parts.length === 0
    ? null
    : `Historical exit rule: ${parts.join('; ')}. Backtested (hypothetical).`;
}
