/** Filtering the ideas: by best decision, and hiding names reporting earnings soon. */
import type { Idea } from '@/entities/idea';

export const EARNINGS_SOON_DAYS = 14;

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
    const days = idea.daysToEarnings;
    return !(filters.hideEarningsSoon && days !== null && days >= 0 && days < EARNINGS_SOON_DAYS);
  });
}

/** The best decisions present, in the ideas' order of first appearance by strength. */
export function decisionsPresent(ideas: readonly Idea[]): string[] {
  return [...new Set(ideas.map((idea) => idea.best.decision))];
}
