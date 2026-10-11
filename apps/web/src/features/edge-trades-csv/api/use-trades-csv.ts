/**
 * Saves the trades of an edge's verdict basis for a period as the CSV file the server writes
 * (`GET /files/edges/{id}/trades.csv`: the same rows, licence redaction and withheld out-of-sample
 * trades as the page). The file route needs the user's token, so it is fetched, not linked.
 */
import { saveTextFile } from '@algotrade/ui';
import { useMutation } from '@tanstack/react-query';

import type { TradePeriod } from '@/entities/edge';
import { api, unwrap } from '@/shared/api';

export function useTradesCsv(edgeId: string) {
  return useMutation({
    mutationFn: async (period: TradePeriod) => {
      const filePeriod = period.toLowerCase() as Lowercase<TradePeriod>;
      const text = await unwrap(
        api.GET('/files/edges/{edge_id}/trades.csv', {
          params: { path: { edge_id: edgeId }, query: { period: filePeriod } },
          parseAs: 'text',
        }),
      );
      saveTextFile(`${edgeId}-trades-${filePeriod}.csv`, text);
    },
  });
}
