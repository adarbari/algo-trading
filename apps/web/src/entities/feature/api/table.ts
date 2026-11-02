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
    $filters: [FilterInput!]
    $q: String
    $sort: String
    $page: Int
    $size: Int
  ) {
    table(
      columns: $columns
      keys: $keys
      filters: $filters
      q: $q
      sort: $sort
      page: $page
      size: $size
    ) {
      session {
        date
        unavailable {
          kind
          features
          guideTerm
          kindText
          cause {
            links {
              level
              subject
              status
              message
              runId
            }
          }
        }
      }
      universeSnapshot
      preSnapshot
      sort
      total
      page
      size
      unavailable {
        kind
        features
        guideTerm
        kindText
        cause {
          links {
            level
            subject
            status
            message
            runId
          }
        }
      }
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
      kinds
      facets {
        total
        matched
        items {
          id
          active
          removes
          unknown
          options {
            value
            count
          }
          bins {
            lo
            hi
            count
          }
        }
      }
      kindTexts {
        kind
        text
      }
    }
  }
`);

const select = (data: gqlTypes.FeatureTableQuery) => (data.table ? toTableData(data.table) : null);

/** A page of the table `query` asks for; the previous page stays on screen while one loads. */
export function useFeatureTable(query: FeatureTableQuery, enabled = true) {
  const variables = tableVariables(query);
  return useQuery({
    queryKey: queryKeys.gql('FeatureTable', variables),
    queryFn: ({ queryKey }) => gql(FeatureTable, variables, queryKey),
    select,
    enabled,
    placeholderData: keepPreviousData,
  });
}

/** One page of the table without a hook, for code that loads on demand (the app's search). */
export function fetchFeatureTable(query: FeatureTableQuery) {
  const variables = tableVariables(query);
  return gql(FeatureTable, variables, queryKeys.gql('FeatureTable', variables)).then(select);
}
