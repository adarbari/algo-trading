/**
 * The parts of a draft answer (docs/drafting/describe-it-plan.md "Explained parts"): the sentence
 * as the server split it, one entry per part with the ids of the criteria, formulas, unresolved
 * terms, missing features and suggestions it owns. The server decides every offset, kind and
 * reference (ADR 0038); this module reads them (an older answer has none) and
 * compares the trader's own edits to the answer's original rows. Pure.
 */
import { tableFor, toCriterion } from '@/entities/screen';
import type { components } from '@/shared/api';

import { same } from './readings';
import type { ScreenDraft } from './review';

export type DraftPart = components['schemas']['Part'];
export type PartKind = DraftPart['kind'];
export type DraftSuggestion = components['schemas']['Suggestion'];

/** The parts of an answer in sentence order; empty for an answer that carries none (the degrade). */
export function partsOf(answer: ScreenDraft): readonly DraftPart[] {
  return answer.parts ?? [];
}

/** The suggestions the trader may accept: soft or score checks only, whatever arrives. */
export function suggestionsOf(answer: ScreenDraft): readonly DraftSuggestion[] {
  return (answer.suggestions ?? []).filter(
    ({ criterion }) => criterion['mode'] === 'soft' || criterion['mode'] === 'score',
  );
}

type Table = Record<string, unknown>;

function tableOf(value: unknown): Table {
  return typeof value === 'object' && value !== null ? (value as Table) : {};
}

function without(table: Table, keys: ReadonlySet<string>): Table {
  return Object.fromEntries(Object.entries(table).filter(([key]) => !keys.has(key)));
}

/**
 * Did the trader change this part's rows? True when a row the answer gave the part is gone from
 * `current`, or is neither the answer's own row nor that row with one of the part's own
 * alternative readings in place of the default (picking one is the answer's option, not an
 * edit; a typed value that is none of them is). Compares the trader's own document to the
 * answer's; no statistics.
 */
export function partEdited(
  part: DraftPart,
  original: unknown,
  current: unknown,
  terms: ScreenDraft['unresolved'],
): boolean {
  const own = (terms ?? []).filter((term) => part.unresolved.includes(term.term));
  // Both sides as the Builder writes a row (it adds the mode and op the server leaves off).
  const written = (id: string, row: Table) => tableFor(toCriterion(id, row));
  return part.criteria.some((id) => {
    const was = tableOf(original)[id];
    if (was === undefined) return false;
    const rawNow = tableOf(current)[id];
    if (rawNow === undefined) return true;
    const now = written(id, tableOf(rawNow));
    if (same(written(id, tableOf(was)), now)) return false;
    return !own.some((term) => {
      const readingKeys = new Set(term.alternatives.flatMap((alt) => Object.keys(alt.criterion)));
      const rest = without(tableOf(was), readingKeys);
      return term.alternatives.some((alt) => same(written(id, { ...rest, ...alt.criterion }), now));
    });
  });
}

/**
 * The rows `partEdited` compares against once `replaced` was redrafted and `next` is the answer:
 * the redrafted part's rows (and any new ones) as `next` has them, every other row as the trader
 * first saw it, so an edit to another part still shows (and still asks before it is replaced).
 */
export function baselineAfter(before: unknown, next: ScreenDraft, replaced: DraftPart): unknown {
  return {
    ...tableOf(next.document['criteria']),
    ...without(tableOf(before), new Set(replaced.criteria)),
  };
}
