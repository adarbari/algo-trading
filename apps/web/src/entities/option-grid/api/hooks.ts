/**
 * Read hook for an instrument's option yield grid over GraphQL (ADR 0037, ADR 0083 amendment
 * 2026-11-01): derived figures per delta band and expiry bucket, never a vendor bid, ask, last
 * or size (fitness test `tests/architecture/options/test_trader_option_figures.py`).
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

const OptionGrid = graphql(`
  query OptionGrid($key: String!) {
    instrument(key: $key) {
      instrumentId
      optionGrid {
        __typename
        ... on OptionGrid {
          underlyingId
          session
          pricedAt
          qKnown
          bands
          columns {
            bucket
            expiry
            days
            reportInside
            reportInsideUnknown {
              code
              kind
              guideTerm
              kindText
            }
            gap {
              code
              kind
              guideTerm
              kindText
            }
          }
          puts {
            __typename
            ... on GridCell {
              band
              strike
              delta
              iv
              mid
              roc
              yieldAnn
              breakeven
              pBelow
              spreadPct
              openInterest
            }
            ... on Unknown {
              code
              kind
              guideTerm
              kindText
            }
          }
          calls {
            __typename
            ... on GridCell {
              band
              strike
              delta
              iv
              mid
              roc
              yieldAnn
              breakeven
              pBelow
              spreadPct
              openInterest
            }
            ... on Unknown {
              code
              kind
              guideTerm
              kindText
            }
          }
        }
        ... on Unknown {
          code
          kind
          guideTerm
          kindText
        }
      }
    }
  }
`);

/** The grid of the session (`instrument` null: no such ticker). */
export function useOptionGrid(key: string | null) {
  const variables = { key: key ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('OptionGrid', variables),
    queryFn: ({ queryKey }) => gql(OptionGrid, variables, queryKey),
    select: (data: gqlTypes.OptionGridQuery) => data.instrument,
    enabled: Boolean(key),
  });
}
