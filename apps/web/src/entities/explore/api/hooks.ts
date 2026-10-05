/**
 * Read hooks for Explore's compare chart over GraphQL (ADR 0037): the compare set's daily
 * closes (split-adjusted) from a start date to the session, one request for the whole set
 * (the instruments of a keyed feature table, their bars through one batched read). The ticker
 * table and the side-by-side values are the feature table (`@/entities/feature`).
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

import { toCompared } from '../model/compare';

const ComparePrices = graphql(`
  query ComparePrices($keys: [String!]!, $start: Date!) {
    table(columns: [], keys: $keys) {
      instruments {
        instrumentId
        symbol
        prices(start: $start) {
          bars {
            session
            close
          }
        }
      }
    }
  }
`);

const select = (data: gqlTypes.ComparePricesQuery) => toCompared(data.table?.instruments ?? []);

/** Each ticker's closes from `start` to the session, in the order given. */
export function useComparePrices(symbols: readonly string[], start: string) {
  const variables = { keys: [...symbols], start };
  return useQuery({
    queryKey: queryKeys.gql('ComparePrices', variables),
    queryFn: () => gql(ComparePrices, variables),
    select,
    enabled: symbols.length > 0,
    placeholderData: keepPreviousData,
  });
}
