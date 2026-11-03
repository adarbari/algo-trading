/** Entity: the event-study scope list for the Admin Event scope page (ADR 0050; Admin only). */
export { refreshEventScope, useEventScope } from './api/queries';
export { eventScope as eventScopeFixture, removedName, scopeName } from './model/fixtures';
export {
  addedBy,
  isTicker,
  reasonLabel,
  sourceLabel,
  START_PAGE,
  TERM_OF_ADD,
  TERM_OF_LAST_REVIEW,
  TERM_OF_MACRO,
  TERM_OF_MOVES,
  TERM_OF_REASONS,
  TERM_OF_REMOVED,
  TERM_OF_SCOPE_NAME,
  TERM_OF_SOURCE,
  TERM_OF_STALE,
  TERM_OF_UNRESOLVED,
} from './model/labels';
export type { EventScope, RemovedName, ScopeName } from './model/types';
