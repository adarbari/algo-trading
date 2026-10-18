/**
 * The words a group shows (labels only; what a group means is the Guide's `criterion_group` and
 * `group_all` / `group_any` / `group_none` entries, ADR 0051), apart from the group edits so a
 * page that only draws a group does not load them.
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
