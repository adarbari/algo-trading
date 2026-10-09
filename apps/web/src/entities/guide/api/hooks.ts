/**
 * The Guide reads (ADR 0051, ADR 0037): `Query.guideIndex` (the sections with their entry
 * counts, the field theme groups, the intents, the playbook families, the situations),
 * `Query.guideField` (what the server derives for one field's page: its reads and caveats split
 * at the names they mention, related fields, the playbooks that use it, the situations that
 * fool it), `Query.guidePlaybook`, `Query.guideSituation`, `Query.guideIndicator` and
 * `Query.guideEpisode` (the market regime's indicators and reference falls), `Query.guideTerm`
 * and `Query.guideStartPage` (the glossary and the Start here how-tos); the four entry reads
 * (term, start page, indicator, episode) go through the page's one `Query.guideEntries` batch
 * (`batch.ts`) under their own query keys. The field's own facts and guide
 * entry come from the catalogue (entities/feature).
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import { loadEpisode, loadIndicator, loadStartPage, loadTerm } from './batch';

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
      families {
        id
        title
        playbooks {
          id
          name
        }
      }
      situations {
        name
        fields
        slug
      }
      indicators {
        key
        plainName
        pace
      }
      episodes {
        key
        name
      }
      startPages {
        id
        order
        title
        summary
      }
      terms {
        id
        term
        short
      }
    }
  }
`);

const GuideFieldQuery = graphql(`
  query GuideField($name: FeatureName!) {
    guideField(name: $name) {
      readsLinked {
        segments {
          text
          field
        }
      }
      caveatsLinked {
        segments {
          text
          field
        }
      }
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
        slug
        signsLinked {
          segments {
            text
            field
          }
        }
      }
    }
  }
`);

const GuidePlaybookQuery = graphql(`
  query GuidePlaybook($id: String!) {
    guidePlaybook(id: $id) {
      id
      name
      family
      familyTitle
      version
      prose {
        summary {
          segments {
            text
            field
          }
        }
        hit {
          segments {
            text
            field
          }
        }
        notChecked {
          segments {
            text
            field
          }
        }
        beforeActing {
          segments {
            text
            field
          }
        }
        sources
      }
      criteria {
        name
        asks
        field
        rule
        mode
        onMiss
      }
      tieBreak
      tieBreakDescending
      related {
        id
        name
        reason
      }
      situations {
        slug
        name
        fields
      }
    }
  }
`);

const GuideSituationQuery = graphql(`
  query GuideSituation($slug: String!) {
    guideSituation(slug: $slug) {
      slug
      name
      signs {
        segments {
          text
          field
        }
      }
      do {
        segments {
          text
          field
        }
      }
      affects
      playbooks {
        id
        name
        fields
      }
    }
  }
`);

/** One glossary term's page (null data: no such term). */
export function useGuideTerm(id: string) {
  const variables = { id };
  return useQuery({
    queryKey: queryKeys.gql('GuideTerm', variables),
    queryFn: () => loadTerm(variables.id),
    select: (data) => data.guideTerm,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}

/** One Start here page (null data: no such page). */
export function useGuideStartPage(id: string) {
  const variables = { id };
  return useQuery({
    queryKey: queryKeys.gql('GuideStartPage', variables),
    queryFn: () => loadStartPage(variables.id),
    select: (data) => data.guideStartPage,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}

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

/** One site playbook's page (null data: no such playbook). */
export function useGuidePlaybook(id: string) {
  const variables = { id };
  return useQuery({
    queryKey: queryKeys.gql('GuidePlaybook', variables),
    queryFn: () => gql(GuidePlaybookQuery, variables),
    select: (data) => data.guidePlaybook,
    staleTime: GUIDE_STALE_MS,
  });
}

/** One situation's page (null data: no such situation). */
export function useGuideSituation(slug: string) {
  const variables = { slug };
  return useQuery({
    queryKey: queryKeys.gql('GuideSituation', variables),
    queryFn: () => gql(GuideSituationQuery, variables),
    select: (data) => data.guideSituation,
    staleTime: GUIDE_STALE_MS,
  });
}

/** One regime indicator's page (null data: no such indicator). */
export function useGuideIndicator(key: string) {
  const variables = { key };
  return useQuery({
    queryKey: queryKeys.gql('GuideIndicator', variables),
    queryFn: () => loadIndicator(variables.key),
    select: (data) => data.guideIndicator,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}

/** One reference market fall's page (null data: no such episode). */
export function useGuideEpisode(slug: string) {
  const variables = { slug };
  return useQuery({
    queryKey: queryKeys.gql('GuideEpisode', variables),
    queryFn: () => loadEpisode(variables.slug),
    select: (data) => data.guideEpisode,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}
