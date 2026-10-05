/**
 * Filtering the ideas: by best decision, and hiding names reporting earnings soon. "Soon" is
 * counted in sessions, the unit the server stores (`rollup.earnings@v1.days_to_earnings`); an
 * idea whose next report is not known is kept.
 */
import type { Idea } from '@/entities/idea';

import { sessionsToEarnings } from './facts';

export const EARNINGS_SOON_SESSIONS = 14;

/** The filter chip's label (the unit is sessions, not calendar days). */
export const EARNINGS_SOON_LABEL = `Hide earnings within ${EARNINGS_SOON_SESSIONS} sessions`;

export interface IdeaFilters {
  /** Best decisions to keep; empty keeps all. */
  decisions: readonly string[];
  hideEarningsSoon: boolean;
}

export const NO_FILTERS: IdeaFilters = { decisions: [], hideEarningsSoon: false };

export function filterIdeas(ideas: readonly Idea[], filters: IdeaFilters): Idea[] {
  return ideas.filter((idea) => {
    if (filters.decisions.length > 0 && !filters.decisions.includes(idea.best.decision)) {
      return false;
    }
    const sessions = sessionsToEarnings(idea);
    return !(
      filters.hideEarningsSoon &&
      sessions !== null &&
      sessions >= 0 &&
      sessions < EARNINGS_SOON_SESSIONS
    );
  });
}

/** The best decisions present, in the ideas' order of first appearance by strength. */
export function decisionsPresent(ideas: readonly Idea[]): string[] {
  return [...new Set(ideas.map((idea) => idea.best.decision))];
}
