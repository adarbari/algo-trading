/**
 * The one adapter for the user's appearance (ADR 0085): the stored theme is read through GraphQL
 * `Query.appearance` and written through REST `PUT /preferences/appearance` (writes stay REST,
 * ADR 0037). Only this module names the path. A save shows at once (the cache is set before the
 * request) and is kept for the session if the write fails; the device copy follows the choice.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { api, gql, graphql, queryKeys, unwrap, type gqlTypes } from '@/shared/api';

import { isThemeChoice, writeDeviceTheme, type ThemeChoice } from '../model/theme';

const AppearanceQuery = graphql(`
  query Appearance {
    appearance {
      theme
    }
  }
`);

const appearanceKey = queryKeys.gql('Appearance', {});

/**
 * The theme to apply: the user's stored choice once known (and mirrored on this device), else
 * `undefined` (the page keeps what its inline script set). Off until `enabled` (a signed-in user).
 */
export function useTheme(enabled: boolean): ThemeChoice | undefined {
  const { data } = useQuery({
    enabled,
    queryKey: appearanceKey,
    queryFn: ({ queryKey }) => gql(AppearanceQuery, {}, queryKey),
    select: (answer) => answer.appearance.theme,
  });
  const theme = isThemeChoice(data) ? data : undefined;
  useEffect(() => {
    if (theme !== undefined) writeDeviceTheme(theme);
  }, [theme]);
  return theme;
}

/** Saves the user's theme choice; the page follows it straight away. */
export function useSaveTheme() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (theme: ThemeChoice) =>
      unwrap(api.PUT('/preferences/appearance', { body: { theme } })),
    onMutate: (theme) => {
      client.setQueryData<gqlTypes.AppearanceQuery>(appearanceKey, { appearance: { theme } });
    },
  });
}
