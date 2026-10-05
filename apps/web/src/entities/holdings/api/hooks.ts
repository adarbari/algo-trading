/** Read hook for an ETF's holdings over GraphQL (ADR 0037), by ticker or instrument id. */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const EtfHoldings = graphql(`
  query EtfHoldings($key: String!, $top: Int!) {
    instrument(key: $key) {
      instrumentId
      isEtf
      holdings(top: $top) {
        asOf
        source
        total
        items {
          rank
          name
          symbol
          weight
          assetClass
          instrument {
            symbol
          }
        }
      }
    }
  }
`);

/**
 * The `top` largest holdings as of the issuer's date the session sees. `holdings` is null for
 * a non-ETF; an ETF with nothing stored has no items.
 */
export function useEtfHoldings(key: string | null, top: number) {
  const variables = { key: key ?? '', top };
  return useQuery({
    queryKey: queryKeys.gql('EtfHoldings', variables),
    queryFn: () => gql(EtfHoldings, variables),
    select: (data: gqlTypes.EtfHoldingsQuery) => data.instrument,
    enabled: Boolean(key),
  });
}
