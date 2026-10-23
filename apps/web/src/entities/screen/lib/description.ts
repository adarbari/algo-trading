/** A screen's one-line description (what it finds): the pure edits the Builder's save form applies. */
import type { ScreenDocument } from '../model/spec';

/** What the server accepts as a description (`ScreenSpec`): one line, at most this long. */
export const MAX_DESCRIPTION_LENGTH = 140;

/** The text as one line (newlines become spaces, runs of spaces one) cut to the length the server accepts. */
export function oneLine(text: string): string {
  return text
    .replace(/\s*[\r\n]+\s*/g, ' ')
    .replace(/ {2,}/g, ' ')
    .slice(0, MAX_DESCRIPTION_LENGTH);
}

/** The screen's description: the draft's own, else the base's (a preset's), else ''. */
export function descriptionOf(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
): string {
  const own = document['description'] ?? base?.['description'];
  return typeof own === 'string' ? own : '';
}

/** The document with its description set (as one line); an empty text writes the key as '' to clear a base's. */
export function withDescription(document: ScreenDocument, text: string): ScreenDocument {
  return { ...document, description: oneLine(text) };
}
