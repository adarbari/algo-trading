/**
 * The popover's detail, read when it first opens (the pill's first click; ADR 0037): the datasets
 * with their share, when the session completed and how many of the viewer's screeners it touches.
 * `admin` adds each gap's cause (the API refuses it to anyone else, ADR 0056). Everything is the
 * server's; the hook only shapes it.
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

export function useDataStatusDetail(admin: boolean) {
  return useQuery({
    queryKey: queryKeys.gql('DataStatus', { admin }),
    queryFn: ({ queryKey }) => gql(DataStatus, { admin }, queryKey),
    select: (data): DataStatusView | null => (data.session ? dataStatusOf(data.session) : null),
  });
}
