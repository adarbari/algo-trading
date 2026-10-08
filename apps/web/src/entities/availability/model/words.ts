/**
 * A gap in words, for a table cell or a tooltip (ADR 0056). A gap is worded by its public
 * `kind`, never by its `code`: a NO_ROW behind a failed step is SYSTEM. Only a stored null that
 * is the fact (EXPLAINED, with its NullReason) is worded by its reason. The kind's own generic
 * line comes from the server (`kindText`), never from here.
 */
import type { gqlTypes } from '@/shared/api';

import type { UnavailableKindName } from './served';

export type UnknownCodeName = gqlTypes.UnknownCode;
export type NullReasonName = gqlTypes.NullReason;

/** The word for a stored null that is the fact (ADR 0046, EXPLAINED); exhaustive over the reasons. */
export function reasonLabel(reason: NullReasonName): string {
  switch (reason) {
    case 'NO_TRADE':
      return 'No trade';
    case 'NOT_ANNOUNCED':
      return 'Not announced';
    case 'NEW_LISTING':
      return 'New listing';
    case 'FEW_BARS':
      return 'Too few trades';
    default: {
      const unreachable: never = reason;
      return unreachable;
    }
  }
}

/** One line on what an explained absence means. */
export function reasonText(reason: NullReasonName): string {
  switch (reason) {
    case 'NO_TRADE':
      return 'no trade on this session: no bar';
    case 'NOT_ANNOUNCED':
      return 'the next report date is not announced';
    case 'NEW_LISTING':
      return 'listed too recently for the window';
    case 'FEW_BARS':
      return 'trades too rarely to fill the window';
    default: {
      const unreachable: never = reason;
      return unreachable;
    }
  }
}

/** What a cell with no value shows: the reason's word, "n/a", "Illiquid", else "Unknown". */
export function cellWord(
  kind: UnavailableKindName | null | undefined,
  code: UnknownCodeName | null | undefined,
  reason?: NullReasonName | null,
): string {
  if (code === 'EXPLAINED' && reason) return reasonLabel(reason);
  if (kind === 'NOT_APPLICABLE') return 'n/a';
  if (kind === 'ILLIQUID') return 'Illiquid';
  return 'Unknown';
}

/**
 * A cell's tooltip: the reason's line for an explained null, what the field's null means for a
 * stored null with no failure behind it (NOT_STORED), else the kind's generic words as the
 * server sent them (`kindText` of the cell).
 */
export function cellText(
  kind: UnavailableKindName | null | undefined,
  code: UnknownCodeName | null | undefined,
  kindText: string | null | undefined,
  nullMeaning?: string | null,
  reason?: NullReasonName | null,
): string {
  if (code === 'EXPLAINED' && reason) return reasonText(reason);
  if (!kind) return 'not known';
  if (kind === 'NOT_STORED' && nullMeaning) return nullMeaning;
  return kindText || 'not known';
}
