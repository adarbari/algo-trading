/**
 * An `Unknown` in words: the one place a value's gap is read (ADR 0056). A stored null that is
 * the fact (EXPLAINED) says what it means; everything else says its public kind in the
 * server's generic words, except that a stored null with no failure behind it (NOT_STORED) says
 * what the field's null means.
 */
import type { ServedUnknown } from './served';
import { cellWord, reasonText } from './words';

/** Why the value is not known, one line (a tooltip, a hint). */
export function unknownText(
  unknown: ServedUnknown | null | undefined,
  nullMeaning?: string | null,
): string {
  if (!unknown) return 'not known';
  if (unknown.code === 'EXPLAINED' && unknown.reason) return reasonText(unknown.reason);
  if (unknown.kind === 'NOT_STORED' && nullMeaning) return nullMeaning;
  return unknown.kindText;
}

/** The short word a cell shows in place of the value ("n/a", "Illiquid", the reason, "Unknown"). */
export function unknownWord(unknown: ServedUnknown | null | undefined): string {
  return unknown ? cellWord(unknown.kind, unknown.code, unknown.reason) : 'Unknown';
}
