/**
 * The feature table over GraphQL (ADR 0037): one page of instruments x catalogue columns for
 * the latest session per request, filtered, sorted and paged on the server (the universe), or
 * the instruments asked for (compare).
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

import { tableVariables, toTableData, type FeatureTableQuery } from '../model/table';

const FeatureTable = graphql(`
  query FeatureTable(
    $columns: [FeatureName!]!
    $keys: [String!]
    $securityType: String
    $sector: String
    $liquidityClass: String
    $leveraged: Boolean
    $optionable: Boolean
    $q: String
    $sort: String
    $page: Int
    $size: Int
  ) {
    table(
      columns: $columns
      keys: $keys
      securityType: $securityType
      sector: $sector
      liquidityClass: $liquidityClass
      leveraged: $leveraged
      optionable: $optionable
      q: $q
      sort: $sort
      page: $page
      size: $size
    ) {
      session {
        date
        missing
      }
      universeSnapshot
      preSnapshot
      sort
      total
      page
      size
      missing
      columns {
        name
        description
        format
        unit
        dtype
        nullMeaning
        licence
        scope
      }
      instruments {
        instrumentId
        symbol
        name
      }
      rows
      unknown
      reasons
    }
  }
`);

const select = (data: gqlTypes.FeatureTableQuery) => (data.table ? toTableData(data.table) : null);

/** A page of the table `query` asks for; the previous page stays on screen while one loads. */
export function useFeatureTable(query: FeatureTableQuery, enabled = true) {
  const variables = tableVariables(query);
  return useQuery({
    queryKey: queryKeys.gql('FeatureTable', variables),
    queryFn: () => gql(FeatureTable, variables),
    select,
    enabled,
    placeholderData: keepPreviousData,
  });
}
