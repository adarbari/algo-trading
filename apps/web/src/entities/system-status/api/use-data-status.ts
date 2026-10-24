/**
 * The data-status pill's state: the status strip's own request (its operation selects
 * `session.dataStatus { state }`, ADR 0037), so the pill adds no read on page load. Null while
 * pending, on a failed read and when there is no session: the pill is then absent, never wrong.
 * The popover's detail is a separate read on the first click (`use-data-status-detail.ts`).
 */
import { useQuery } from '@tanstack/react-query';

import { pillOf, type PillView } from '../model/data-status';

import { statusStripQuery } from './queries';

export function useDataStatus(admin: boolean): PillView | null {
  return (
    useQuery({
      ...statusStripQuery(admin),
      select: (data): PillView | null => (data.session?.dataStatus ? pillOf(data.session) : null),
    }).data ?? null
  );
}
