/** The event-scope entity's types, as the operation selects them. */
import type { gqlTypes } from '@/shared/api';

export type EventScope = NonNullable<gqlTypes.EventScopeQuery['eventScope']>;
export type ScopeName = EventScope['names'][number];
export type RemovedName = EventScope['removed'][number];
