/**
 * The filters in force on a table, list or feed, as the URL carries them (ADR 0082,
 * docs/ui/filtering.md): one entry per filter id, switched on or off.
 *
 * TODO: the server's filter definitions and the `FilterInput` GraphQL type land later; these
 * hand-declared types are replaced by the generated ones then.
 */

/** A window's unit: calendar days (`d`) or trading sessions (`s`). */
export type FilterUnit = 'days' | 'sessions';

/** "Within N days / sessions": the `..5s` form. */
export interface FilterWindow {
  amount: number;
  unit: FilterUnit;
}

/** One filter: pick values, a numeric range, or a window (at most one of the three). */
export interface FilterState {
  id: string;
  /** A pick's chosen values. */
  values?: string[];
  /** A range's bounds (either may be open). */
  min?: number;
  max?: number;
  within?: FilterWindow;
  /** False: switched off (kept, in no mask). */
  active: boolean;
}

/** A change to one filter: `undefined` removes a key. */
export type FilterPatch = { [K in keyof Omit<FilterState, 'id'>]?: FilterState[K] | undefined };
