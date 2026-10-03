/** Read hooks for the feature catalogue and one feature's distribution across the universe. */
import { useQuery } from '@tanstack/react-query';

import { api, queryKeys, unwrap } from '@/shared/api';

/** The catalogue changes only with a release or a user's feature file: cache it longer. */
const CATALOGUE_STALE_MS = 10 * 60_000;

export function useFeatureCatalogue() {
  return useQuery({
    queryKey: queryKeys.features.catalogue(),
    queryFn: () => unwrap(api.GET('/features')),
    staleTime: CATALOGUE_STALE_MS,
  });
}

export function useFeatureDistribution(name: string | null) {
  return useQuery({
    queryKey: queryKeys.features.distribution(name ?? ''),
    queryFn: () =>
      unwrap(api.GET('/features/{name}/distribution', { params: { path: { name: name ?? '' } } })),
    enabled: Boolean(name),
    staleTime: CATALOGUE_STALE_MS,
  });
}
