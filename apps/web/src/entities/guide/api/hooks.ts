/**
 * The Guide reads (ADR 0051, ADR 0037): `Query.guideIndex` (the sections with their entry
 * counts, the field theme groups, the intents) and `Query.guideField` (what the server derives
 * for one field's page: related fields, the playbooks that use it, the situations that fool it).
 * The field's own facts and guide entry come from the catalogue (entities/feature).
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

/** The Guide changes with a release or a config edit: cache it as long as the catalogue. */
const GUIDE_STALE_MS = 10 * 60_000;

const GuideIndexQuery = graphql(`
  query GuideIndex {
    guideIndex {
      sections {
        id
        title
        purpose
        entries
      }
      themeGroups {
        id
        title
        themes {
          theme
          fields
        }
      }
      intents {
        intent
        fields
      }
    }
  }
`);

const GuideFieldQuery = graphql(`
  query GuideField($name: FeatureName!) {
    guideField(name: $name) {
      related
      playbooks {
        id
        name
        family
        rules
        column
        rank
        flag
      }
      situations {
        name
        signs
        do
        affects
      }
    }
  }
`);

export function useGuideIndex() {
  return useQuery({
    queryKey: queryKeys.gql('GuideIndex', {}),
    queryFn: () => gql(GuideIndexQuery, {}),
    select: (data) => data.guideIndex,
    staleTime: GUIDE_STALE_MS,
  });
}

/** One field's server-derived page parts; nothing is read without a name. */
export function useGuideField(name: string | null) {
  const variables = { name: name ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('GuideField', variables),
    queryFn: () => gql(GuideFieldQuery, variables),
    select: (data) => data.guideField,
    enabled: Boolean(name),
    staleTime: GUIDE_STALE_MS,
  });
}
