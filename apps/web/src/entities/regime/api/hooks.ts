/**
 * The market regime reads (ADR 0047, ADR 0037): `Regime` is everything about the session's
 * regime but its history (label as weather, headline, scores, indicator cards with their
 * values, sizing) and `RegimeBands` the label history of a window as bands. Both go through the
 * one `Query.regime`; one `Regime` response is shared by every embedding (top bar, Ideas strip,
 * Regime page), so the cache key is the operation alone.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { Regime, RegimeBand } from '../model/regime';

/** The GraphQL operations' names: their cached responses share these key prefixes. */
export const REGIME_OPERATION = 'Regime';
export const REGIME_BANDS_OPERATION = 'RegimeBands';

const RegimeQuery = graphql(`
  query Regime {
    regime {
      session
      label
      headline
      unknownReason {
        code
        detail
      }
      scores {
        macroRisk {
          value
          unknown {
            code
            detail
          }
        }
        marketStress {
          value
          unknown {
            code
            detail
          }
        }
        fragility {
          value
          unknown {
            code
            detail
          }
        }
      }
      sizing {
        label
        multiplier
      }
      indicators {
        key
        pace
        plainName
        technicalName
        oneLiner
        whyItMatters
        whatOnMeans
        before {
          episode
          line
        }
        leadTime
        falseAlarms
        links {
          title
          url
        }
        value
        unknown {
          code
          detail
        }
        format
        status
        changed
      }
    }
  }
`);

const RegimeBandsQuery = graphql(`
  query RegimeBands($start: Date!, $end: Date!) {
    regime {
      bands(start: $start, end: $end) {
        start
        end
        label
      }
    }
  }
`);

/** The session's regime (null: nothing stored for the session; UNKNOWN is a label, not null). */
export function useRegime() {
  return useQuery({
    queryKey: queryKeys.gql(REGIME_OPERATION, {}),
    queryFn: () => gql(RegimeQuery, {}),
    select: (data): Regime | null => data.regime ?? null,
  });
}

/**
 * The label history of `start..end` (`end` on or before the regime's session: pass a stored
 * session date, never today). Waits until `end` is known.
 */
export function useRegimeBands(start: string, end: string | undefined) {
  const variables = { start, end: end ?? '' };
  return useQuery({
    queryKey: queryKeys.gql(REGIME_BANDS_OPERATION, variables),
    queryFn: () => gql(RegimeBandsQuery, variables),
    enabled: end !== undefined,
    select: (data): readonly RegimeBand[] => data.regime?.bands ?? [],
  });
}
