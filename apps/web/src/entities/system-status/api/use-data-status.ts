/**
 * The session's data status for the pill: its own small read (`Session.dataStatus`, ADR 0037),
 * started when the pill's lazy chunk loads, so it blocks nothing and its document stays out of
 * the entry chunk (which is at its budget); the status strip's operation is unchanged. `admin`
 * adds each gap's cause (the API refuses it to anyone else, ADR 0056). Null while pending, on a
 * failed read and when there is no session: the pill is then absent, never wrong.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { dataStatusOf, type DataStatusView } from '../model/data-status';

const DataStatus = graphql(`
  query DataStatus($admin: Boolean!) {
    session {
      date
      newer {
        date
      }
      dataStatus {
        state
        knowledgeTs
        datasets {
          name
          status
          share
          unavailable {
            kindText
            cause @include(if: $admin) {
              links {
                level
                subject
                status
                message
              }
            }
          }
        }
        affectedScreeners
        totalScreeners
      }
    }
  }
`);

export function useDataStatus(admin: boolean): DataStatusView | null {
  return (
    useQuery({
      queryKey: queryKeys.gql('DataStatus', { admin }),
      queryFn: ({ queryKey }) => gql(DataStatus, { admin }, queryKey),
      select: (data): DataStatusView | null => (data.session ? dataStatusOf(data.session) : null),
    }).data ?? null
  );
}
