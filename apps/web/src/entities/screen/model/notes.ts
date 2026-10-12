/** A screen's notes (what it does not cover): the pure edits the Builder applies while describing. */
import type { ScreenDocument } from './spec';

/** What the server accepts as a screen's notes (`ScreenSpec`): at most this many, this long. */
export const MAX_NOTES = 10;
export const MAX_NOTE_LENGTH = 200;

const listOf = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

/** What the screen does not cover (a missing feature the trader asked for): the draft's own list, else the base's. */
export function notesOf(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
): string[] {
  return listOf(document['notes'] ?? base?.['notes']);
}

/**
 * `notes` joined to `current`, in order: blanks and repeats left out, each cut to the length the
 * server accepts, the list capped.
 */
export function mergeNotes(current: readonly string[], added: readonly string[]): string[] {
  const out = [...current];
  for (const raw of added) {
    const note = raw.trim().slice(0, MAX_NOTE_LENGTH);
    if (note !== '' && !out.includes(note)) out.push(note);
  }
  return out.slice(0, MAX_NOTES);
}

/**
 * The document with its notes set. An empty list is written as `notes: []` only to clear the ones
 * `base` (the preset it extends) carries; when the base has none the key goes (an empty list
 * would change the document's hash for nothing).
 */
export function withNotes(
  document: ScreenDocument,
  notes: readonly string[],
  base?: Readonly<Record<string, unknown>> | null,
): ScreenDocument {
  if (notes.length === 0 && listOf(base?.['notes']).length === 0) {
    const { notes: _dropped, ...rest } = document;
    return rest;
  }
  return { ...document, notes: [...notes] };
}
