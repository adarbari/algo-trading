/**
 * The one adapter for a user's saved views of a table (read model WEB 7): read through GraphQL
 * `Query.view(scope, name)`, written through REST `PUT` / `DELETE
 * /preferences/views/{scope}/view` (writes stay REST, ADR 0037). Only this module names the
 * preferences path. A view is the user's, never the screener's: no version, no hash.
 */
import { useMutation, useQuery, useQueryClient, type Query } from '@tanstack/react-query';

import { api, gql, graphql, queryKeys, unwrap, type gqlTypes } from '@/shared/api';

import type { ViewContent } from '../model/view';

export const TABLE_VIEW_OPERATION = 'TableView';

const TableView = graphql(`
  query TableView($scope: String!, $name: String) {
    view(scope: $scope, name: $name) {
      scope
      name
      saved
      columns
      narrowColumns
      sort
      decisions
      names
    }
  }
`);

export type SavedView = NonNullable<gqlTypes.TableViewQuery['view']>;

const keyOf = (scope: string, name: string | null) =>
  queryKeys.gql(TABLE_VIEW_OPERATION, { scope, name });

/** The user's view of the table `scope`: the default one, or the one called `name`. */
export function useSavedView(scope: string, name: string | null) {
  return useQuery({
    queryKey: keyOf(scope, name),
    queryFn: () => gql(TableView, { scope, name }),
    select: (data) => data.view,
  });
}

/** The cached views of `scope`, but the one called `except` (their list of names changed). */
const viewsOf = (scope: string, except?: string | null) => (query: Query) => {
  const variables = query.queryKey[2] as { scope?: string; name?: string | null } | undefined;
  return (
    variables?.scope === scope && (except === undefined || (variables.name ?? null) !== except)
  );
};

/** Saves a view of `scope` (the default one, or a named one). */
export function useSaveView(scope: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, view }: { name: string | null; view: ViewContent }) =>
      unwrap(
        api.PUT('/preferences/views/{scope}/view', {
          params: { path: { scope }, query: { name } },
          body: {
            columns: [...view.columns],
            narrow_columns: [...view.narrowColumns],
            sort: view.sort,
            decisions: [...view.decisions],
          },
        }),
      ),
    onSuccess: (saved, { name }) => {
      const { narrow_columns: narrowColumns, ...rest } = saved;
      client.setQueryData<gqlTypes.TableViewQuery>(keyOf(scope, name), {
        view: { ...rest, narrowColumns },
      });
      void client.invalidateQueries({
        queryKey: queryKeys.gqlAll(TABLE_VIEW_OPERATION),
        predicate: viewsOf(scope, name),
      });
    },
  });
}

/** Removes a named view of `scope`. */
export function useDeleteView(scope: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(
        api.DELETE('/preferences/views/{scope}/view', {
          params: { path: { scope }, query: { name } },
        }),
      ),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: queryKeys.gqlAll(TABLE_VIEW_OPERATION),
        predicate: viewsOf(scope),
      }),
  });
}
