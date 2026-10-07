/**
 * Read hook for one field's help (`Query.guideField`, ADR 0037 / 0051): the field's info with
 * the site field guide's entry (reads, its first sentence, the criterion per intent, caveats).
 * The button reads it on mount for its hover summary; the drawer shows the same cached read.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

/** The guide changes only with a release: cache it as long as the catalogue. */
const GUIDE_STALE_MS = 10 * 60_000;

const GuideHelpField = graphql(`
  query GuideHelpField($name: FeatureName!) {
    guideField(name: $name) {
      info {
        name
        unit
        guide {
          theme
          reads
          summary
          caveats
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
  }
`);

/** A field's help by catalogue name. */
export function useGuideHelp(name: string) {
  const variables = { name };
  return useQuery({
    queryKey: queryKeys.gql('GuideHelpField', variables),
    queryFn: () => gql(GuideHelpField, variables),
    select: (data) => data.guideField?.info ?? null,
    staleTime: GUIDE_STALE_MS,
    retry: false,
  });
}
