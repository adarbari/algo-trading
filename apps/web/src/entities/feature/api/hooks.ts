/**
 * Read hooks for the feature catalogue (each field with the site field guide's entry, ADR 0041
 * amended) and one feature's distribution across the universe, over GraphQL (`Query.catalogue`,
 * `Query.distribution`; ADR 0037). The distribution is for exactly
 * the latest session: a feature not stored for it comes back with `unknown` and no counts.
 */
import { useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

/** The catalogue changes only with a release or a user's feature file: cache it longer. */
const CATALOGUE_STALE_MS = 10 * 60_000;

const FeatureCatalogue = graphql(`
  query FeatureCatalogue {
    catalogue {
      name
      kind
      source
      dtype
      format
      description
      nullMeaning
      version
      group
      key
      inputs
      unit
      range
      categories
      scope
      owner
      licence
      guide {
        theme
        reads
        summary
        caveats
        sources
        uses {
          intent
          op
          value
          mode
          tolerance
          onMiss
          note
        }
      }
    }
  }
`);

const FeatureDistribution = graphql(`
  query FeatureDistribution($name: FeatureName!) {
    distribution(name: $name) {
      name
      session
      count
      nulls
      quantiles {
        q
        value
      }
      histogram {
        lo
        hi
        count
      }
      categories {
        value
        count
      }
      unknown {
        code
        kind
        guideTerm
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
      passing {
        intent
        count
        bins
      }
    }
  }
`);

export function useFeatureCatalogue() {
  return useQuery({
    queryKey: queryKeys.gql('FeatureCatalogue', {}),
    queryFn: () => gql(FeatureCatalogue, {}),
    select: (data) => data.catalogue,
    staleTime: CATALOGUE_STALE_MS,
  });
}

/** Read the catalogue again (a user feature was saved). */
export function refreshCatalogue(client: QueryClient): Promise<void> {
  return client.invalidateQueries({ queryKey: queryKeys.gql('FeatureCatalogue', {}) });
}

/** `name` across the universe for the latest session; null: nothing stored at all. */
export function useFeatureDistribution(name: string | null) {
  const variables = { name: name ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('FeatureDistribution', variables),
    queryFn: () => gql(FeatureDistribution, variables),
    select: (data) => data.distribution,
    enabled: Boolean(name),
    staleTime: CATALOGUE_STALE_MS,
  });
}
