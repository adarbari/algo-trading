/**
 * How the top-ideas table reads an idea's served facts (ADR 0038): which of the values the
 * server sent to show, never a value computed in the browser (docs/api/read-model.md
 * "Presentation is not derivation"). The Earnings cell shows the next report date, else a muted
 * "Last <d MMM>" from the last report date, else the UNKNOWN label with the server's reason.
 */
import { formatValue } from '@algotrade/ui';

import { factOf, IDEA_FACTS, type Idea } from '@/entities/idea';
import { isUnknown, unknownLabel, unknownReason } from '@/entities/feature';

/** The label of a value the server does not have for the session. */
export const UNKNOWN_LABEL = 'Unknown';

export interface FactCell {
  text: string;
  muted: boolean;
  /** Why the shown value is what it is (an UNKNOWN reason), for a tooltip. */
  title?: string;
}

const text = (value: unknown): string | null =>
  typeof value === 'string' && value !== '' ? value : null;

const number = (value: unknown): number | null => (typeof value === 'number' ? value : null);

/** The next earnings date (ISO), if the server has one for the session. */
export function nextEarnings(idea: Idea): string | null {
  return text(factOf(idea, IDEA_FACTS.nextEarnings)?.value);
}

/** The Earnings cell: next date, else "Last <d MMM>", else UNKNOWN with the reason. */
export function earningsCell(idea: Idea): FactCell {
  const next = nextEarnings(idea);
  if (next) {
    return { text: formatValue(next, { kind: 'date', style: 'weekday' }).text, muted: false };
  }
  const nextFact = factOf(idea, IDEA_FACTS.nextEarnings);
  const last = text(factOf(idea, IDEA_FACTS.lastEarnings)?.value);
  const shown = last
    ? `Last ${formatValue(last, { kind: 'date', style: 'day' }).text}`
    : unknownLabel(nextFact?.unknown?.code);
  return isUnknown(nextFact)
    ? { text: shown, muted: true, title: unknownReason(nextFact) }
    : { text: shown, muted: true };
}

/** Sessions to the next report (`days_to_earnings` counts sessions); null: not known. */
export function sessionsToEarnings(idea: Idea): number | null {
  return number(factOf(idea, IDEA_FACTS.sessionsToEarnings)?.value);
}

/** Calendar days to the nearest listed expiry; null: not known (`dteReason` says why). */
export function expiryDte(idea: Idea): number | null {
  return number(factOf(idea, IDEA_FACTS.expiryDte)?.value);
}

export function dteReason(idea: Idea): string | undefined {
  const fact = factOf(idea, IDEA_FACTS.expiryDte);
  return isUnknown(fact) ? unknownReason(fact) : undefined;
}

/** The VRP gate's IV30 (a fraction); null: not known. */
export function iv30(idea: Idea): number | null {
  return number(factOf(idea, IDEA_FACTS.iv30)?.value);
}
