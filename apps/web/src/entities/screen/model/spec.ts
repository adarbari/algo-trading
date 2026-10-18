/**
 * A rule screen as the Builder edits it (docs/screeners/rules.md): the draft document (the
 * screen's TOML keys as JSON) and its criteria. A draft that extends a preset holds only the
 * user's overrides; the criteria shown are the working copy resolved through its layers (the
 * API's `working`), with the draft's own changes merged on top by id. Pure.
 */
import { feature, type gqlTypes } from '@/shared/api';

import { groupsOf, pruneGroups, type CriterionGroup } from '../lib/groups';

type ServedDetail = NonNullable<gqlTypes.ScreenDetailQuery['screenDetail']>;
type Table = Record<string, unknown>;

/** One screen as `screenDetail` serves it; its JSON documents are TOML tables (objects). */
export type ScreenerDetail = Omit<ServedDetail, 'draft' | 'working'> & {
  draft: Table | null;
  working: Table | null;
};
export type ScreenerListItem = gqlTypes.MyScreensQuery['myScreens'][number];
export type ScreenerSummary = gqlTypes.ScreenerConfigsQuery['configs'][number];
export type PresetPin = NonNullable<ServedDetail['preset']>;

export type CriterionMode = 'hard' | 'soft' | 'score';
export type MissDecision = 'WATCH' | 'LIQUIDITY_RISK' | 'EVENT_RISK';
/** A number (absolute, in the field's unit) or a share of the threshold. */
export type Tolerance = number | { relative: number };

/** One criterion: the keys of a `[criteria.<id>]` table. */
export interface Criterion {
  id: string;
  field: string;
  op: string;
  value?: unknown;
  mode: CriterionMode;
  tolerance?: Tolerance | undefined;
  on_miss?: MissDecision | undefined;
  /** The group it sits in (ADR 0071), as `criteriaOf` reads it; never stored on the criterion. */
  group?: string | undefined;
}

type CriteriaTable = Record<string, Record<string, unknown>>;

/** The draft document: a screen's TOML keys as JSON. */
export interface ScreenDocument extends Record<string, unknown> {
  id: string;
  criteria?: CriteriaTable;
  /** The boolean groups (`[groups.<id>]`: one of all / any / none, a list of member ids). */
  groups?: Record<string, Record<string, unknown>>;
}

/** The keys the authoring flow manages (a draft never carries them). */
const MANAGED_KEYS = ['version', 'schedule'];

export const MODES: readonly CriterionMode[] = ['hard', 'soft', 'score'];
export const MISS_DECISIONS: readonly MissDecision[] = ['WATCH', 'LIQUIDITY_RISK', 'EVENT_RISK'];

/** Ops that take no threshold. */
export const NO_VALUE_OPS: readonly string[] = ['is_null', 'not_null'];

const tableOf = (value: unknown): CriteriaTable =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as CriteriaTable) : {};

/** A document without the keys the authoring flow manages. */
export function toDocument(source: Readonly<Record<string, unknown>>, id: string): ScreenDocument {
  const kept = Object.fromEntries(
    Object.entries(source).filter(([key]) => key !== 'id' && !MANAGED_KEYS.includes(key)),
  );
  return { id, ...kept };
}

/**
 * Who a new screener screens (ADR 0030): a rule screen has no selection, so it opens with the
 * base gates as criteria. They are ordinary criteria: edit or remove any of them.
 */
const BASE_CRITERIA: CriteriaTable = {
  security_type: {
    field: feature('instrument.security_type'),
    op: 'in',
    value: ['COMMON_STOCK', 'ADR', 'ETF'],
  },
  status: { field: feature('instrument.status'), op: 'eq', value: 'ACTIVE' },
  optionable: { field: feature('instrument.optionable'), op: 'eq', value: true },
};

/** A blank draft: a rule screen with the base gates. */
export function blankDocument(id: string): ScreenDocument {
  return { id, kind: 'screener', impl: 'rules', criteria: structuredClone(BASE_CRITERIA) };
}

/** The criterion of a `[criteria.<id>]` table (unknown keys left out). */
export function toCriterion(id: string, table: Record<string, unknown>): Criterion {
  const mode = MODES.find((m) => m === table['mode']) ?? 'hard';
  const criterion: Criterion = {
    id,
    field: typeof table['field'] === 'string' ? table['field'] : '',
    op: typeof table['op'] === 'string' ? table['op'] : 'gte',
    mode,
  };
  if ('value' in table) criterion.value = table['value'];
  if (table['tolerance'] !== undefined) criterion.tolerance = table['tolerance'] as Tolerance;
  if (typeof table['on_miss'] === 'string') criterion.on_miss = table['on_miss'] as MissDecision;
  return criterion;
}

/** The enabled criterion tables in order, before a disabled group takes any out. */
function enabledTables(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
): Map<string, Record<string, unknown>> {
  const merged = new Map<string, Record<string, unknown>>();
  for (const [id, table] of Object.entries(tableOf(base?.['criteria'])))
    merged.set(id, { ...table });
  for (const [id, table] of Object.entries(tableOf(document.criteria))) {
    merged.set(id, { ...merged.get(id), ...table });
  }
  return new Map([...merged].filter(([, table]) => table['enabled'] !== false));
}

/**
 * The enabled groups (ADR 0071) and the ids a disabled group takes out, merged through the
 * layers like the criteria.
 */
function groupState(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
  live: ReadonlySet<string>,
) {
  return groupsOf(base?.['groups'], document.groups, live);
}

/**
 * The enabled criteria in order: the working copy's (`base`, resolved through the preset)
 * first, then any the draft added; the draft's keys win per criterion; `enabled = false`
 * removes one, and so does a disabled group; `group` names the group a criterion sits in.
 */
export function criteriaOf(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
): Criterion[] {
  const enabled = enabledTables(base, document);
  const { groups, off } = groupState(base, document, new Set(enabled.keys()));
  const parent = new Map(groups.flatMap((g) => g.members.map((m) => [m, g.id] as const)));
  return [...enabled]
    .filter(([id]) => !off.has(id))
    .map(([id, table]) => {
      const criterion = toCriterion(id, table);
      const group = parent.get(id);
      return group === undefined ? criterion : { ...criterion, group };
    });
}

/** The enabled groups of the working copy (ADR 0071), members that are gone removed. */
export function groupsFor(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
): CriterionGroup[] {
  return groupState(base, document, new Set(enabledTables(base, document).keys())).groups;
}

/** The base's criterion ids (they cannot be deleted from a draft, only switched off). */
function baseIds(base: Readonly<Record<string, unknown>> | null | undefined): Set<string> {
  return new Set(Object.keys(tableOf(base?.['criteria'])));
}

/** Every criterion id in use, switched off or not (a new criterion must not reuse one). */
export function criterionIds(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
): string[] {
  const groups = [
    ...Object.keys(tableOf(base?.['groups'])),
    ...Object.keys(tableOf(document.groups)),
  ];
  // criteria and groups share one key space
  return [...new Set([...baseIds(base), ...Object.keys(tableOf(document.criteria)), ...groups])];
}

/** The table the document holds for `criterion` (its keys but the id). */
export const tableFor = (criterion: Criterion): Record<string, unknown> => {
  const { id: _id, group: _group, ...keys } = criterion;
  return Object.fromEntries(Object.entries(keys).filter(([, v]) => v !== undefined));
};

/** The document with `criterion` set (added, or replacing the whole table of its id). */
export function withCriterion(document: ScreenDocument, criterion: Criterion): ScreenDocument {
  const table = tableFor(criterion);
  // A criterion switched off earlier comes back on: the draft's table says so explicitly.
  return { ...document, criteria: { ...tableOf(document.criteria), [criterion.id]: table } };
}

/** The document without a criterion: dropped if the draft added it, else switched off. */
export function withoutCriterion(
  document: ScreenDocument,
  base: Readonly<Record<string, unknown>> | null | undefined,
  id: string,
): ScreenDocument {
  const rest = Object.fromEntries(
    Object.entries(tableOf(document.criteria)).filter(([key]) => key !== id),
  );
  // a draft group loses the member, and dissolves when it is left too small
  return pruneGroups(
    {
      ...document,
      criteria: baseIds(base).has(id) ? { ...rest, [id]: { enabled: false } } : rest,
    },
    [id],
  );
}

/** Is the criterion ready to run (a field, and a threshold where its op needs one)? */
export function isComplete(criterion: Criterion): boolean {
  if (!criterion.field) return false;
  if (NO_VALUE_OPS.includes(criterion.op)) return true;
  if (criterion.value === undefined || criterion.value === null || criterion.value === '') {
    return false;
  }
  if (Array.isArray(criterion.value)) {
    return criterion.value.length > 0 && criterion.value.every((v) => v !== null && v !== '');
  }
  return criterion.mode === 'soft' ? criterion.tolerance !== undefined : true;
}

/** The document as the preview takes it: criteria still being filled in are left out. */
export function previewDocument(document: ScreenDocument): ScreenDocument {
  const kept: CriteriaTable = {};
  const left: string[] = [];
  for (const [id, table] of Object.entries(tableOf(document.criteria))) {
    if (table['enabled'] === false || isComplete(toCriterion(id, table))) kept[id] = table;
    else left.push(id);
  }
  return pruneGroups({ ...document, criteria: kept }, left);
}

/** An unused criterion id from its field (`rollup.iv30@v1.iv30` -> `iv30`). */
export function newCriterionId(taken: readonly string[], field = ''): string {
  const column = field.slice(field.lastIndexOf('.') + 1).replace(/[^A-Za-z0-9_-]/g, '_');
  const stem = (column || 'criterion').slice(0, 56);
  let id = stem;
  for (let n = 2; taken.includes(id); n += 1) id = `${stem}_${String(n)}`;
  return id;
}

/** The criterion a server error names: `<screen>.criteria.<id>.<field>: ...`. */
export function criterionOfError(message: string | null | undefined): string | null {
  return /\.criteria\.([A-Za-z0-9_-]+)\./.exec(message ?? '')?.[1] ?? null;
}

/** A screen id the API accepts: 1-64 of [a-z0-9_-]. */
export const isScreenId = (id: string): boolean => /^[a-z0-9_-]{1,64}$/.test(id);

/** The tie-break column of the draft (`[rank] tie_break`), if any. */
export function tieBreakOf(
  base: Readonly<Record<string, unknown>> | null | undefined,
  document: ScreenDocument,
): { field: string | null; order: 'asc' | 'desc' } {
  const rank = { ...plainTable(base?.['rank']), ...plainTable(document['rank']) };
  // An empty tie_break in the draft clears the one the preset sets.
  const field =
    typeof rank['tie_break'] === 'string' && rank['tie_break'] !== '' ? rank['tie_break'] : null;
  return { field, order: rank['tie_break_order'] === 'asc' ? 'asc' : 'desc' };
}

function plainTable(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/**
 * The document with its tie-break column set. `null` clears it: dropped from a screen of its
 * own, set to "" in a copy of a preset (which may set one: a user layer cannot delete a key).
 */
export function withTieBreak(
  document: ScreenDocument,
  field: string | null,
  order: 'asc' | 'desc',
): ScreenDocument {
  const rank = { ...plainTable(document['rank']) };
  if (field === null) {
    delete rank['tie_break_order'];
    if (document['extends'] === undefined) delete rank['tie_break'];
    else rank['tie_break'] = '';
  } else {
    rank['tie_break'] = field;
    rank['tie_break_order'] = order;
  }
  return { ...document, rank };
}
