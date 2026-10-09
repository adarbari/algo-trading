/**
 * Filtering the ideas by the Ideas page's search params (the view in use and the filter chips):
 * a choice among the values the server sent, never a computed one. "Soon" is counted in
 * sessions, the unit the server stores (`rollup.earnings@v1.days_to_earnings`); an idea whose
 * next report is not known is kept. The chips' options are the values present in the ideas.
 */
import type { Idea, IdeaFilterKey, IdeasSearch } from '@/entities/idea';
import { LIQUIDITY_VALUES } from '@/entities/idea';
import { decisionLabel } from '@/entities/screen';

import { sessionsToEarnings } from './facts';

export const EARNINGS_SOON_SESSIONS = 14;

/** The decision the "High conviction" view keeps. */
export const CONVICTION_DECISION = 'QUALIFIED';

const LIQUIDITY_RISK = 'liquidity_risk';

const LIQUIDITY_LABELS = { ok: 'No liquidity risk', risk: 'Liquidity risk' } as const;

const earningsSoon = (idea: Idea): boolean => {
  const sessions = sessionsToEarnings(idea);
  return sessions !== null && sessions >= 0 && sessions < EARNINGS_SOON_SESSIONS;
};

const hasLiquidityRisk = (idea: Idea): boolean =>
  idea.watchOut.some((w) => w.id === LIQUIDITY_RISK);

const MATCH: Record<IdeaFilterKey, (idea: Idea, value: string) => boolean> = {
  screener: (idea, value) => idea.picks.some((p) => p.screenerId === value),
  decision: (idea, value) => idea.best.decision === value,
  liq: (idea, value) => hasLiquidityRisk(idea) === (value === 'risk'),
  regime: (idea, value) => idea.regime === value,
};

export function filterIdeas(ideas: readonly Idea[], search: IdeasSearch): Idea[] {
  return ideas.filter((idea) => {
    if (search.view === 'conviction' && idea.best.decision !== CONVICTION_DECISION) return false;
    if (search.view === 'no-earnings' && earningsSoon(idea)) return false;
    return (Object.keys(MATCH) as IdeaFilterKey[]).every((key) => {
      const value = search[key];
      return value === undefined || MATCH[key](idea, value);
    });
  });
}

/** The chip's name for each filter. */
export const FILTER_TITLES: Record<IdeaFilterKey, string> = {
  screener: 'Screener',
  decision: 'Decision',
  liq: 'Liquidity',
  regime: 'Regime',
};

export interface FilterOption {
  value: string;
  label: string;
}

/** The values a filter chip offers: only those some idea has (liquidity always offers both). */
export function filterOptions(ideas: readonly Idea[], key: IdeaFilterKey): FilterOption[] {
  switch (key) {
    case 'screener': {
      const names = new Map<string, string>(
        ideas.flatMap((i) => i.picks.map((p): [string, string] => [p.screenerId, p.screenerName])),
      );
      return [...names].map(([value, label]) => ({ value, label }));
    }
    case 'decision':
      return [...new Set(ideas.map((i) => i.best.decision))].map((value) => ({
        value,
        label: decisionLabel(value),
      }));
    case 'liq':
      return LIQUIDITY_VALUES.map((value) => ({ value, label: LIQUIDITY_LABELS[value] }));
    case 'regime':
      return [...new Set(ideas.flatMap((i) => (i.regime === null ? [] : [i.regime])))].map(
        (value) => ({ value, label: value }),
      );
  }
}

/** The label of the value a chip holds (the value itself when no idea has it any more). */
export function optionLabel(ideas: readonly Idea[], key: IdeaFilterKey, value: string): string {
  return filterOptions(ideas, key).find((o) => o.value === value)?.label ?? value;
}
