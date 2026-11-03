/** How the Event scope page words the list's keys. Labels only: what a term means is a Guide entry. */
import type { ScopeName } from './types';

export const TERM_OF_SCOPE_NAME = 'event_scope_name';
export const TERM_OF_REASONS = 'event_scope_reasons';
export const TERM_OF_SOURCE = 'event_scope_source';
export const TERM_OF_LAST_REVIEW = 'event_scope_last_review';
export const TERM_OF_STALE = 'event_scope_stale';
export const TERM_OF_MOVES = 'event_scope_moves';
export const TERM_OF_MACRO = 'event_scope_macro';
export const TERM_OF_REMOVED = 'event_scope_removed';
export const TERM_OF_UNRESOLVED = 'event_scope_unresolved';
export const TERM_OF_ADD = 'event_scope_add';
export const START_PAGE = 'read_event_scope';

/** The words of a reason's key (the server sends the keys; their meaning is the Guide's). */
const REASON_LABEL: Readonly<Record<string, string>> = {
  tier: 'Put tier',
  list: 'Site list',
  requested: 'Requested',
  reference: 'Fund reference',
};

export const reasonLabel = (reason: string) => REASON_LABEL[reason] ?? reason;

export const sourceLabel = (source: string) => (source === 'admin' ? 'Admin' : 'Site file');

/** Who added an admin entry and when (the day), empty for a name of the site file. */
export const addedBy = (name: ScopeName) =>
  name.source === 'admin' && name.by ? `${name.by}, ${name.at?.slice(0, 10) ?? name.addedOn}` : '';

/** A symbol the server takes: 1-12 letters, digits, `.` or `-` (the server resolves it again). */
export const isTicker = (symbol: string) => /^[A-Za-z0-9.-]{1,12}$/.test(symbol.trim());
