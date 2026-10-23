/**
 * The session's data status for the pill: the same one request as the status strip (its
 * operation selects `dataStatus`, ADR 0037), so the pill adds no read and blocks nothing; the
 * hook only selects and shapes it, so its code ships with the pill's lazy chunk, not the entry.
 * `admin` adds each gap's cause to that request (the API refuses it to anyone else, ADR 0056).
 * Null while pending, on a failed read and when there is no session: the pill is then absent,
 * never wrong.
 */
import { useQuery } from '@tanstack/react-query';

import { dataStatusOf, type DataStatusView } from '../model/data-status';

import { statusStripQuery } from './queries';

export function useDataStatus(admin: boolean): DataStatusView | null {
  return (
    useQuery({
      ...statusStripQuery(admin),
      select: (data): DataStatusView | null =>
        data.session?.dataStatus ? dataStatusOf(data.session) : null,
    }).data ?? null
  );
}
