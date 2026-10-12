/**
 * The parts of a draft answer (docs/drafting/describe-it-plan.md "Explained parts"): the sentence
 * as the server split it, one entry per part with the ids of the criteria, formulas, unresolved
 * terms, missing features and suggestions it owns. The server decides every offset, kind and
 * reference (ADR 0038); this module reads them (an older answer has none) and
 * compares the trader's own edits to the answer's original rows. Pure.
 */
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
 * `current`, or differs from the answer's own. Picking another reading of one of the part's
 * unresolved terms is the answer's own option, not an edit: the keys the readings set are left
 * out of the comparison. Compares the trader's own document to the answer's; no statistics.
 */
export function partEdited(
  part: DraftPart,
  original: unknown,
  current: unknown,
  terms: ScreenDraft['unresolved'],
): boolean {
  const readingKeys = new Set(
    (terms ?? [])
      .filter((term) => part.unresolved.includes(term.term))
      .flatMap((term) => term.alternatives.flatMap((alt) => Object.keys(alt.criterion))),
  );
  return part.criteria.some((id) => {
    const was = tableOf(original)[id];
    if (was === undefined) return false;
    const now = tableOf(current)[id];
    if (now === undefined) return true;
    return !same(without(tableOf(was), readingKeys), without(tableOf(now), readingKeys));
  });
}
