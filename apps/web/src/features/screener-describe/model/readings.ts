/**
 * The readings of an ambiguous term ("liquid"): each alternative the server gave carries its own
 * ready criterion, so picking one is a local swap of one row of the Builder's document, with no
 * second model call. The document holds the default's criterion under some id (or the one picked
 * last): the row is found by equality with the alternative currently loaded, and replaced.
 * The pick is recorded as a `choice_made` event (ADR 0066). Pure.
 */
import { toCriterion, type Criterion, type ScreenDocument } from '@/entities/screen';
import type { components } from '@/shared/api';

export type Unresolved = components['schemas']['Unresolved'];
type Table = Record<string, unknown>;

function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) || Array.isArray(b)) {
    return (
      Array.isArray(a) &&
      Array.isArray(b) &&
      a.length === b.length &&
      a.every((item, i) => same(item, b[i]))
    );
  }
  const left = a as Table;
  const right = b as Table;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every((k) => same(left[k], right[k]));
}

/** The id of the row of `document` that holds `reading`'s keys (the first one), else null. */
export function rowOfReading(
  document: ScreenDocument,
  reading: Readonly<Record<string, unknown>>,
): string | null {
  const rows = Object.entries(document.criteria ?? {});
  const found = rows.find(([, table]) =>
    Object.entries(reading).every(([key, value]) => same(table[key], value)),
  );
  return found?.[0] ?? null;
}

/**
 * The criterion that replaces the row holding reading `from` of `term` with reading `to`: the row's
 * id, the new reading's keys. Null when the row is not there any more (the trader removed or
 * rewrote it) or an index is out of range: the swap is then not offered.
 */
export function readingSwap(
  document: ScreenDocument,
  term: Unresolved,
  from: number,
  to: number,
): Criterion | null {
  const current = term.alternatives[from];
  const next = term.alternatives[to];
  if (!current || !next) return null;
  const id = rowOfReading(document, current.criterion);
  return id === null ? null : toCriterion(id, next.criterion);
}
