/**
 * Narrowing the Edges index by the filters the server offers (asset, side, holding band) and a
 * search text: which edges match and which mechanism cards stay. It only selects rows the
 * server sent; the counts, labels and bands are the server's.
 */
import type { EdgeRowValue } from '@/entities/guide';

export interface EdgeRowFacts extends EdgeRowValue {
  asset: string;
  holdingBand: string;
}

export interface EdgeFilters {
  asset?: string | undefined;
  side?: string | undefined;
  holding?: string | undefined;
  /** The search text as typed. */
  query: string;
}

/** Whether any of the three structured filters is in force (the search text is not one). */
export function filtering(filters: EdgeFilters): boolean {
  return Boolean(filters.asset ?? filters.side ?? filters.holding);
}

const has = (text: string, query: string): boolean =>
  query.trim() === '' || text.toLowerCase().includes(query.trim().toLowerCase());

/** An edge passes the structured filters and, when there is a search text, names it. */
export function edgeMatches(edge: EdgeRowFacts, filters: EdgeFilters): boolean {
  return (
    (!filters.asset || edge.asset === filters.asset) &&
    (!filters.side || edge.side === filters.side) &&
    (!filters.holding || edge.holdingBand === filters.holding) &&
    has(`${edge.name} ${edge.thesis}`, filters.query)
  );
}

export interface CardFacts {
  title: string;
  question: string;
  short: string;
  examples: string;
  edges: readonly EdgeRowFacts[];
}

/**
 * A card stays when one of its edges passes the filters, or, with no structured filter in
 * force, when the search text names the mechanism itself.
 */
export function cardMatches(card: CardFacts, filters: EdgeFilters): boolean {
  if (card.edges.some((edge) => edgeMatches(edge, filters))) return true;
  return (
    !filtering(filters) &&
    has(`${card.title} ${card.question} ${card.short} ${card.examples}`, filters.query)
  );
}

/** An idea passes the search text (an idea has no asset, side or holding to filter by). */
export function ideaMatches(idea: { title: string; whyNotBuilt: string }, query: string): boolean {
  return has(`${idea.title} ${idea.whyNotBuilt}`, query);
}
