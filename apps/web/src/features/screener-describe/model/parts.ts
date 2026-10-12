/**
 * The parts of a draft answer (docs/drafting/describe-it-plan.md "Explained parts"): the sentence
 * as the server split it, one entry per part with the ids of the criteria, formulas, unresolved
 * terms, missing features and suggestions it owns. The server decides every offset, kind and
 * reference (ADR 0038); this module reads them defensively (an older answer has none) and
 * compares the trader's own edits to the answer's original rows. Types are local until the
 * generated client carries `parts`; replace them then. Pure.
 */
import { same } from './readings';
import type { ScreenDraft } from './review';

export type PartKind = 'applied' | 'formula' | 'needs_choice' | 'not_available' | 'not_understood';
export type PartOrigin = 'words' | 'kept' | 'unplaced';

export interface DraftPart {
  id: string;
  words: string;
  start: number;
  end: number;
  /** The part in plain language; null when the server found it inconsistent with the rows. */
  reading: string | null;
  reading_source: 'model' | 'server' | null;
  kind: PartKind;
  origin: PartOrigin;
  criteria: string[];
  dropped: unknown[];
  formulas: string[];
  unresolved: string[];
  missing: string[];
  suggestions: string[];
}

export type DraftSuggestion = NonNullable<ScreenDraft['suggestions']>[number] & { id: string };

const KINDS: readonly PartKind[] = [
  'applied',
  'formula',
  'needs_choice',
  'not_available',
  'not_understood',
];
const ORIGINS: readonly PartOrigin[] = ['words', 'kept', 'unplaced'];

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function toPart(raw: unknown): DraftPart | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  const kind = KINDS.find((k) => k === r['kind']);
  if (typeof r['id'] !== 'string' || !kind) return null;
  const source = r['reading_source'];
  return {
    id: r['id'],
    words: typeof r['words'] === 'string' ? r['words'] : '',
    start: typeof r['start'] === 'number' ? r['start'] : 0,
    end: typeof r['end'] === 'number' ? r['end'] : 0,
    reading: typeof r['reading'] === 'string' && r['reading'] !== '' ? r['reading'] : null,
    reading_source: source === 'model' || source === 'server' ? source : null,
    kind,
    origin: ORIGINS.find((o) => o === r['origin']) ?? 'words',
    criteria: strings(r['criteria']),
    dropped: Array.isArray(r['dropped']) ? r['dropped'] : [],
    formulas: strings(r['formulas']),
    unresolved: strings(r['unresolved']),
    missing: strings(r['missing']),
    suggestions: strings(r['suggestions']),
  };
}

/** The parts of an answer in sentence order; empty for an answer that carries none (the degrade). */
export function partsOf(answer: ScreenDraft): readonly DraftPart[] {
  const raw = (answer as { parts?: unknown }).parts;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    const part = toPart(item);
    return part ? [part] : [];
  });
}

/**
 * The suggestions of an answer, each under the id the server gave it (the parts reference
 * them by it); until it does, the position stands in for it. Only soft or score checks are
 * offered: a hard one is never a suggestion, whatever arrives.
 */
export function suggestionsOf(answer: ScreenDraft): readonly DraftSuggestion[] {
  return (answer.suggestions ?? [])
    .map((suggestion, i) => {
      const id = (suggestion as { id?: unknown }).id;
      return { ...suggestion, id: typeof id === 'string' ? id : String(i + 1) };
    })
    .filter(({ criterion }) => criterion['mode'] === 'soft' || criterion['mode'] === 'score');
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
