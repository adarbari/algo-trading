/**
 * The boolean groups of a rule screen as the Builder edits them (ADR 0071, docs/screeners/
 * rules.md "Groups"): the `[groups.<id>]` tables merged through the layers, the tree the Builder
 * lays out (a group sits at its first criterion's place; one level is editable, a deeper tree is
 * one read-only gate), and the pure document edits behind its actions (either this or the
 * previous, exclude, ungroup). Generic over the document so it never imports the spec model.
 */
export type GroupKind = 'all' | 'any' | 'none';

export const GROUP_KINDS: readonly GroupKind[] = ['all', 'any', 'none'];

export const KIND_LABEL: Record<GroupKind, string> = {
  all: 'All of',
  any: 'Any of',
  none: 'None of',
};

export const CONNECTOR_LABEL: Record<GroupKind, string> = {
  all: 'and',
  any: 'or',
  none: 'and not',
};

/** The Guide term of each kind. */
export const KIND_TERM: Record<GroupKind, string> = {
  all: 'group_all',
  any: 'group_any',
  none: 'group_none',
};

/** The word before the member that decided a group's outcome in a pick's scorecard. */
export const DECIDED_BY_LABEL = 'Decided by';

/** The fewest members a group of that kind needs (the server's size rule). */
const MIN_MEMBERS: Record<GroupKind, number> = { all: 2, any: 2, none: 1 };

/** One group: the keys of a `[groups.<id>]` table (members are criterion or group ids). */
export interface CriterionGroup {
  id: string;
  kind: GroupKind;
  members: string[];
}

type Table = Record<string, unknown>;
type Tables = Record<string, Table>;
type Doc = Record<string, unknown>;

const tablesOf = (value: unknown): Tables =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Tables) : {};

const kindOf = (table: Table): GroupKind | undefined =>
  GROUP_KINDS.find((kind) => Array.isArray(table[kind]));

/** The groups a document's own `[groups]` table holds, by id. */
export const ownGroupIds = (document: Doc): Set<string> =>
  new Set(Object.keys(tablesOf(document['groups'])));

/**
 * The enabled groups in order: the base's (resolved through the preset) first, then the draft's
 * own; the draft's keys win per group (its kind replaces the base's); members a layer disabled
 * and everything under a disabled group drop out, as the server does before its size rules
 * (`off`: every id under a disabled group, its own included).
 */
export function groupsOf(
  baseGroups: unknown,
  draftGroups: unknown,
  liveCriteria: ReadonlySet<string>,
): { groups: CriterionGroup[]; off: Set<string> } {
  const merged = new Map<string, Table>();
  for (const [id, table] of Object.entries(tablesOf(baseGroups))) merged.set(id, { ...table });
  for (const [id, table] of Object.entries(tablesOf(draftGroups))) {
    const base = merged.get(id) ?? {};
    const over = kindOf(table)
      ? Object.fromEntries(
          Object.entries(base).filter(([k]) => !GROUP_KINDS.includes(k as GroupKind)),
        )
      : base;
    merged.set(id, { ...over, ...table });
  }
  const members = (table: Table): string[] => {
    const kind = kindOf(table);
    return kind ? (table[kind] as unknown[]).filter((m): m is string => typeof m === 'string') : [];
  };
  const off = new Set<string>();
  const stack = [...merged].filter(([, t]) => t['enabled'] === false).map(([id]) => id);
  while (stack.length > 0) {
    const id = stack.pop() as string;
    if (off.has(id)) continue;
    off.add(id);
    const table = merged.get(id);
    if (table) stack.push(...members(table));
  }
  const groups: CriterionGroup[] = [];
  for (const [id, table] of merged) {
    const kind = kindOf(table);
    if (!kind || off.has(id)) continue;
    const kept = members(table).filter(
      (m) => !off.has(m) && (merged.has(m) || liveCriteria.has(m)),
    );
    groups.push({ id, kind, members: kept });
  }
  return { groups, off };
}

/** Each member's parent group id. */
export function parentsOf(groups: readonly CriterionGroup[]): Map<string, string> {
  const parents = new Map<string, string>();
  for (const group of groups) for (const member of group.members) parents.set(member, group.id);
  return parents;
}

/** A node of the Builder's tree: a criterion, or a group with its members in funnel order. */
export type LayoutNode<C extends { id: string }> =
  | { type: 'criterion'; criterion: C }
  | {
      type: 'group';
      group: CriterionGroup;
      members: LayoutNode<C>[];
      /** The Builder edits it: one level of criteria, written by this draft. */
      editable: boolean;
      /** Every group under it is the draft's own (so Ungroup applies). */
      owned: boolean;
    };

/**
 * The criteria as the Builder shows them: loose criteria and gates (top-level groups) in funnel
 * order, a gate at its first criterion's place, members in criteria order. `own` is the draft's
 * group ids: a group of the preset layer is never edited from here.
 */
export function layoutOf<C extends { id: string }>(
  criteria: readonly C[],
  groups: readonly CriterionGroup[],
  own: ReadonlySet<string>,
): LayoutNode<C>[] {
  const byId = new Map(criteria.map((c, index) => [c.id, { criterion: c, index }]));
  const byGroup = new Map(groups.map((g) => [g.id, g]));
  const parents = parentsOf(groups);
  const position = new Map<string, number>();
  const place = (id: string): number => {
    const known = position.get(id);
    if (known !== undefined) return known;
    const group = byGroup.get(id);
    const at = group
      ? Math.min(...group.members.map(place), Number.MAX_SAFE_INTEGER)
      : (byId.get(id)?.index ?? Number.MAX_SAFE_INTEGER);
    position.set(id, at);
    return at;
  };
  const build = (id: string): LayoutNode<C> | null => {
    const group = byGroup.get(id);
    if (!group) {
      const entry = byId.get(id);
      return entry ? { type: 'criterion', criterion: entry.criterion } : null;
    }
    const members = [...group.members]
      .sort((a, b) => place(a) - place(b))
      .flatMap((m) => build(m) ?? []);
    if (members.length === 0) return null;
    const flat = members.every((m) => m.type === 'criterion');
    const owned = own.has(id) && members.every((m) => m.type === 'criterion' || m.owned);
    return {
      type: 'group',
      group,
      members,
      editable: flat && own.has(id) && group.kind !== 'all' && !parents.has(id),
      owned,
    };
  };
  const roots = [...criteria.map((c) => c.id), ...groups.map((g) => g.id)].filter(
    (id) => !parents.has(id),
  );
  return [...new Set(roots)].sort((a, b) => place(a) - place(b)).flatMap((id) => build(id) ?? []);
}

/** A group as one expression: "A or B", "A and B", "not C". `null`: none of its members is ready. */
export function groupText(
  group: CriterionGroup,
  clauseOf: (id: string) => string | null,
  groups: ReadonlyMap<string, CriterionGroup>,
): string | null {
  const parts = group.members.flatMap((id) => {
    const nested = groups.get(id);
    if (!nested) return clauseOf(id) ?? [];
    const text = groupText(nested, clauseOf, groups);
    if (text === null) return [];
    return nested.kind === 'none' && nested.members.length === 1 ? text : `(${text})`;
  });
  if (parts.length === 0) return null;
  if (group.kind === 'none')
    return `not ${parts.length === 1 ? (parts[0] ?? '') : `(${parts.join(' or ')})`}`;
  return parts.join(group.kind === 'any' ? ' or ' : ' and ');
}

/** The document with `group` written to its `[groups]` table (added, or replacing its table). */
export function withGroup<D extends Doc>(document: D, group: CriterionGroup): D {
  return {
    ...document,
    groups: { ...tablesOf(document['groups']), [group.id]: { [group.kind]: group.members } },
  };
}

/** The document without those groups (and without the key when none is left). */
export function withoutGroups<D extends Doc>(document: D, ids: Iterable<string>): D {
  const gone = new Set(ids);
  const rest = Object.fromEntries(
    Object.entries(tablesOf(document['groups'])).filter(([id]) => !gone.has(id)),
  );
  const { groups: _groups, ...others } = document;
  return (Object.keys(rest).length > 0 ? { ...others, groups: rest } : others) as D;
}

/**
 * The document after ids left the screen (a removed criterion): they leave the draft's own
 * groups; a group left too small dissolves (its members stay as criteria), which may shrink its
 * parent in turn.
 */
export function pruneGroups<D extends Doc>(document: D, gone: Iterable<string>): D {
  const left = new Set(gone);
  let tables = tablesOf(document['groups']);
  for (let changed = true; changed;) {
    changed = false;
    for (const [id, table] of Object.entries(tables)) {
      const kind = kindOf(table);
      if (!kind) continue;
      const members = (table[kind] as string[]).filter((m) => !left.has(m));
      if (
        members.length === (table[kind] as string[]).length &&
        members.length >= MIN_MEMBERS[kind]
      )
        continue;
      changed = true;
      if (members.length >= MIN_MEMBERS[kind]) {
        tables = { ...tables, [id]: { ...table, [kind]: members } };
      } else {
        tables = Object.fromEntries(Object.entries(tables).filter(([key]) => key !== id));
        left.add(id);
      }
    }
  }
  const { groups: _groups, ...others } = document;
  return (Object.keys(tables).length > 0 ? { ...others, groups: tables } : others) as D;
}

/** An unused group id (`any`, `any_2`, `none` ...) in the one key space of criteria and groups. */
export function newGroupId(taken: readonly string[], kind: GroupKind): string {
  let id: string = kind;
  for (let n = 2; taken.includes(id) || id === 'score'; n += 1) id = `${kind}_${String(n)}`;
  return id;
}

/** The loose criterion `id` and the node before it, if they can join as "either this or that". */
export function joinTarget<C extends { id: string }>(
  layout: readonly LayoutNode<C>[],
  id: string,
): { previous: LayoutNode<C> } | null {
  const index = layout.findIndex((n) => n.type === 'criterion' && n.criterion.id === id);
  const previous = layout[index - 1];
  if (index < 1 || !previous) return null;
  if (previous.type === 'criterion') return { previous };
  return previous.editable && previous.group.kind === 'any' ? { previous } : null;
}

/**
 * "Either this or the previous": a new `any` group of the criterion and the loose criterion
 * before it, or the criterion added to the `any` group before it. The document as it was when
 * the two do not join.
 */
export function eitherWithPrevious<C extends { id: string }, D extends Doc>(
  document: D,
  layout: readonly LayoutNode<C>[],
  taken: readonly string[],
  id: string,
): D {
  const target = joinTarget(layout, id);
  if (!target) return document;
  const { previous } = target;
  if (previous.type === 'group') {
    return withGroup(document, { ...previous.group, members: [...previous.group.members, id] });
  }
  return withGroup(document, {
    id: newGroupId(taken, 'any'),
    kind: 'any',
    members: [previous.criterion.id, id],
  });
}

/** "Exclude (none of)": the criterion alone in a new `none` group. */
export function excludeCriterion<D extends Doc>(
  document: D,
  taken: readonly string[],
  id: string,
): D {
  return withGroup(document, { id: newGroupId(taken, 'none'), kind: 'none', members: [id] });
}

/** "Exclude (none of)" on an `any` group: not any of its members. */
export function excludeGroup<D extends Doc>(document: D, group: CriterionGroup): D {
  return withGroup(document, { ...group, kind: 'none' });
}

/**
 * "Ungroup": the gate's group goes and its members become gates; a member `all` group would be a
 * top-level `all` (the screen itself), so it dissolves too, down to the first `any` or `none`.
 */
export function ungroup<D extends Doc>(
  document: D,
  groups: readonly CriterionGroup[],
  id: string,
): D {
  const byId = new Map(groups.map((g) => [g.id, g]));
  const gone: string[] = [];
  const dissolve = (groupId: string) => {
    gone.push(groupId);
    for (const member of byId.get(groupId)?.members ?? []) {
      if (byId.get(member)?.kind === 'all') dissolve(member);
    }
  };
  dissolve(id);
  return withoutGroups(document, gone);
}
