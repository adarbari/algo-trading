/**
 * The regime indicators' sources with their provenance (`RegimeSources`, ADR 0047): apart from
 * `Regime` because the four provenance fields (latest observation, vintage) are read from the
 * stored vintages only when a query selects them; the shell's `Regime` does not, the Regime page
 * does.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { RegimeSources } from '../model/regime';

export const REGIME_SOURCES_OPERATION = 'RegimeSources';

const RegimeSourcesQuery = graphql(`
  query RegimeSources {
    regime {
      indicators {
        key
        sources {
          label
          series
          cadence
          releaseLagDays
          url
          licence
          terms
          lastObservation
          vintageDate
          vintageKind
          firstVintage
          active
        }
      }
    }
  }
`);

/** Each indicator's sources by card key (empty when nothing is stored for the session). */
export function useRegimeSources() {
  return useQuery({
    queryKey: queryKeys.gql(REGIME_SOURCES_OPERATION, {}),
    queryFn: ({ queryKey }) => gql(RegimeSourcesQuery, {}, queryKey),
    select: (data): RegimeSources =>
      new Map((data.regime?.indicators ?? []).map((i) => [i.key, i.sources])),
  });
}
