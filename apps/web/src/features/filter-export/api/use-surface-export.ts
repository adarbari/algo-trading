/**
 * Saves a filter-bar surface's rows under the filters in force as the CSV file the server writes
 * (`GET /files/{surface}.csv?f=`): what the viewer can see, built by the surface's own loader, never
 * from rows the browser holds (a personal-licence value is LICENCE to a non-holder). The file
 * route needs the user's token, so it is fetched, not linked.
 */
import { saveTextFile } from '@algotrade/ui';
import { useMutation } from '@tanstack/react-query';

import { api, unwrap } from '@/shared/api';

export function useSurfaceExport(surface: string) {
  return useMutation({
    mutationFn: async ({ f, session }: { f: string; session?: string | null | undefined }) => {
      const text = await unwrap(
        api.GET('/files/{surface}.csv', {
          params: {
            path: { surface },
            query: { ...(f && { f }), ...(session && { date: session }) },
          },
          parseAs: 'text',
        }),
      );
      saveTextFile(session ? `${surface}-${session}.csv` : `${surface}.csv`, text); // the server's dated name
    },
  });
}
