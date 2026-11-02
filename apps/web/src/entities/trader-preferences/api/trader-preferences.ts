/**
 * The one adapter for the trader's stored choices (ADR 0083, amendment 2026-11-01): the default
 * Ideas tab and the watchlist (instrument ids only, never a position) are read through GraphQL
 * `Query.traderPreferences` and written through REST `PUT /preferences/ideas` and
 * `PUT /preferences/watchlist` (writes stay REST, ADR 0037). A save shows at once (the cache is
 * set before the request) and is put back when the write fails.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, gql, graphql, queryKeys, unwrap, type gqlTypes } from '@/shared/api';

import { isIdeasTab, type IdeasTab } from '../model/tabs';

const TraderPreferencesQuery = graphql(`
  query TraderPreferences {
    traderPreferences {
      defaultTab
      watchlist {
        instrumentId
        symbol
      }
    }
  }
`);

const preferencesKey = queryKeys.gql('TraderPreferences', {});
/** The shell's `Appearance` read also carries the start tab (the sign-up check): kept in step. */
const shellKey = queryKeys.gql('Appearance', {});

/** A name on the watchlist: its id, and its ticker when the session's snapshot has one. */
export interface WatchedName {
  instrumentId: string;
  symbol: string | null;
}

export interface TraderPreferences {
  /** `null`: the sign-up question has not been answered. */
  defaultTab: IdeasTab | null;
  watchlist: readonly WatchedName[];
}

/** The stored choices; off until `enabled` (a signed-in viewer). */
export function useTraderPreferences(enabled = true) {
  return useQuery({
    enabled,
    queryKey: preferencesKey,
    queryFn: ({ queryKey }) => gql(TraderPreferencesQuery, {}, queryKey),
    select: (answer): TraderPreferences => ({
      defaultTab: isIdeasTab(answer.traderPreferences.defaultTab)
        ? answer.traderPreferences.defaultTab
        : null,
      watchlist: answer.traderPreferences.watchlist,
    }),
  });
}

type Cached = gqlTypes.TraderPreferencesQuery;

function useOptimistic<T>(change: (cached: Cached, value: T) => Cached) {
  const client = useQueryClient();
  return {
    onMutate: (value: T) => {
      const before = client.getQueryData<Cached>(preferencesKey);
      if (before) client.setQueryData<Cached>(preferencesKey, change(before, value));
      return { before };
    },
    onError: (_error: Error, _value: T, context: { before: Cached | undefined } | undefined) => {
      if (context?.before) client.setQueryData<Cached>(preferencesKey, context.before);
    },
    onSettled: () => client.invalidateQueries({ queryKey: preferencesKey }),
  };
}

/** Saves the default Ideas tab (the sign-up answer, or a change in Settings). */
export function useSaveIdeasTab() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (tab: IdeasTab) =>
      unwrap(api.PUT('/preferences/ideas', { body: { default_tab: tab } })),
    onSuccess: (_saved, tab) => {
      client.setQueryData<gqlTypes.AppearanceQuery>(shellKey, (cached) =>
        cached ? { ...cached, appearance: { ...cached.appearance, startTab: tab } } : cached,
      );
    },
    ...useOptimistic<IdeasTab>((cached, tab) => ({
      traderPreferences: { ...cached.traderPreferences, defaultTab: tab },
    })),
  });
}

/** Saves the whole watchlist: the instrument ids, in order (the server keeps at most 50). */
export function useSaveWatchlist() {
  return useMutation({
    mutationFn: (names: readonly WatchedName[]) =>
      unwrap(
        api.PUT('/preferences/watchlist', {
          body: { instruments: names.map((n) => n.instrumentId) },
        }),
      ),
    ...useOptimistic<readonly WatchedName[]>((cached, names) => ({
      traderPreferences: { ...cached.traderPreferences, watchlist: [...names] },
    })),
  });
}
