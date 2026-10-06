/**
 * Who is calling (ADR 0040 decision 4): `Query.viewer { id name role workspaces }` over GraphQL.
 * The answer is `null` when the API says 401 (no or expired session), which is how the app
 * knows to show the login page; a 403 (a valid token the registry does not know) stays an
 * error. With the API running `ALGOTRADE_AUTH=off` the viewer answers with no session at all,
 * and that counts as signed in: there is no separate dev mode in the web app.
 */
import { queryOptions, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { ApiError, gql, graphql, onUnauthorized, queryKeys, type gqlTypes } from '@/shared/api';

const ViewerQuery = graphql(`
  query Viewer {
    viewer {
      id
      name
      role
      workspaces
    }
  }
`);

/** The signed-in user as the registry knows them. */
export type Viewer = gqlTypes.ViewerQuery['viewer'];

async function fetchViewer(): Promise<Viewer | null> {
  try {
    return (await gql(ViewerQuery, {})).viewer;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export const viewerKey = queryKeys.gql('Viewer', {});

export const viewerQuery = () => queryOptions({ queryKey: viewerKey, queryFn: fetchViewer });

/** The viewer, from the cache when fresh (for route guards, outside React). */
export function ensureViewer(client: QueryClient): Promise<Viewer | null> {
  return client.query(viewerQuery());
}

/**
 * The viewer for React: `data` is the user, `null` when signed out, undefined while loading.
 * Any 401 anywhere in the app (the API refused the token) turns it into `null`.
 */
export function useViewer() {
  const client = useQueryClient();
  useEffect(
    () =>
      onUnauthorized(() => {
        client.setQueryData(viewerKey, null);
      }),
    [client],
  );
  return useQuery(viewerQuery());
}
