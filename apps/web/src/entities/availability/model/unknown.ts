/**
 * An `Unknown` in words: the one place a value's gap is read (ADR 0056). A stored null that is
 * the fact (EXPLAINED) says what it means; everything else says its public kind, except that a
 * stored null with no failure behind it (NOT_STORED) says what the field's null means.
 */
import { codeReason, reasonLabel, unknownLabel } from '@/entities/feature';

import { KIND_TEXT } from './kinds';
import type { ServedUnknown } from './served';

/** Why the value is not known, one line (a tooltip, a hint). */
export function unknownText(
  unknown: ServedUnknown | null | undefined,
  nullMeaning?: string | null,
): string {
  if (!unknown) return 'not known';
  if (unknown.code === 'EXPLAINED') return codeReason('EXPLAINED', nullMeaning, unknown.reason);
  if (unknown.kind === 'NOT_STORED' && nullMeaning) return nullMeaning;
  return KIND_TEXT[unknown.kind];
}

/** The short word a cell shows in place of the value ("n/a", "Illiquid", the reason, "Unknown"). */
export function unknownWord(unknown: ServedUnknown | null | undefined): string {
  if (!unknown) return 'Unknown';
  if (unknown.code === 'EXPLAINED' && unknown.reason) return reasonLabel(unknown.reason);
  if (unknown.kind === 'NOT_APPLICABLE') return unknownLabel('NOT_APPLICABLE');
  if (unknown.kind === 'ILLIQUID') return unknownLabel('ILLIQUID');
  return unknownLabel(null);
}
