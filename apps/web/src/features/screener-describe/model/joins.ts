/**
 * The connector between two parts of the sentence as the review shows it: which joins get a token
 * and in which label (the server reads the join, ADR 0038; this decides only what is worth
 * showing). A join of "or" or "and not" always shows; a plain "and" shows only when the trader's
 * own word is more than a plain conjunction ("but", "while", "only if"), since that word changes
 * how the second part reads. Pure.
 */
import type { TermRef } from './labels';
import type { DraftPart } from './parts';

export type PartJoinKind = NonNullable<DraftPart['join']>;

/** The trader's register for each logic ("but not": one negation beside a card that states the exclusion). */
const JOIN_LABELS: Record<PartJoinKind, string> = {
  and: 'and',
  or: 'or',
  and_not: 'but not',
};

/** Words that join without adding anything: the token is hidden when every word is one. */
const PLAIN_CONJUNCTIONS: ReadonlySet<string> = new Set(['and', 'with', 'plus', 'also', 'then']);

/** The fixed words of a connector token (labels; its Guide term sits beside it). */
export const JOIN_TEXT = {
  joinedBy: 'joined by',
  readAs: 'read as',
  help: { kind: 'term', id: 'describe_part_join' } satisfies TermRef,
} as const;

function isPlain(words: string): boolean {
  const pieces = words
    .toLowerCase()
    .split(/[\s,]+/)
    .filter((piece) => piece !== '');
  return pieces.every((piece) => PLAIN_CONJUNCTIONS.has(piece));
}

/** What to render before a part's card, or null when the part shows no connector. */
export function joinToken(
  part: Pick<DraftPart, 'join' | 'join_words'>,
): { join: PartJoinKind; label: string; words: string } | null {
  const join = part.join;
  if (join === null || join === undefined) return null;
  const words = part.join_words.trim();
  if (join === 'and' && isPlain(words)) return null;
  return { join, label: JOIN_LABELS[join], words };
}
