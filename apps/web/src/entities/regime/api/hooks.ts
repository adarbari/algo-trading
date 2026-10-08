/**
 * The market regime reads (ADR 0047, ADR 0037): `Regime` is everything about the session's
 * regime but its history (label as weather, headline, scores, indicator cards with their
 * values, sizing) and `RegimeBands` the label history of a window as bands. Both go through the
 * one `Query.regime`; one `Regime` response is shared by every embedding (top bar, Ideas strip,
 * Regime page), so the cache key is the operation alone.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { SeriesHistory } from '../model/history';
import type { Recession, Regime, RegimeBand, RegimeEpisode } from '../model/regime';

/** The GraphQL operations' names: their cached responses share these key prefixes. */
export const REGIME_OPERATION = 'Regime';
export const REGIME_BANDS_OPERATION = 'RegimeBands';
export const REGIME_EPISODES_OPERATION = 'RegimeEpisodes';
export const MARKET_HISTORY_OPERATION = 'MarketHistory';

const RegimeQuery = graphql(`
  query Regime {
    regime {
      session
      label
      headline
      unknownReason {
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
      scores {
        macroRisk {
          value
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
          feature
          coverageFeature
          threshold
        }
        marketStress {
          value
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
          feature
          coverageFeature
          threshold
        }
        fragility {
          value
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
          feature
          coverageFeature
          threshold
        }
      }
      sizing {
        label
        multiplier
        enabled
        unknownMultiplier
        multipliers {
          label
          multiplier
        }
        screeners {
          screenerId
          name
          enabled
          pauseIn
        }
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
        format
        status
        changed
        feature
        verdictFeature
        range {
          min
          max
        }
        threshold
        direction
        how {
          text
          url
        }
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

const RegimeEpisodesQuery = graphql(`
  query RegimeEpisodes {
    regime {
      episodes {
        key
        name
        kind
        peak
        trough
        recovered
        spxDrawdown
        nasdaqDrawdown
        recession
        nberStart
        nberEnd
        cause
        notes
        knownFrom
      }
      recessions {
        start
        end
        announcedStart
        announcedEnd
      }
    }
  }
`);

const MarketHistoryQuery = graphql(`
  query MarketHistory($names: [String!]!, $start: Date!, $end: Date!, $points: Int!) {
    market {
      history(names: $names, start: $start, end: $end, points: $points) {
        name
        bucketSessions
        points {
          session
          value
        }
        segments {
          start
          end
          value
        }
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

/**
 * The reference drawdowns and NBER recessions the session knows (`config/site/regime/
 * episodes.toml`, oldest first; a recovery or a recession's end only once it has come). Empty
 * when nothing is stored for the session.
 */
export function useRegimeEpisodes() {
  return useQuery({
    queryKey: queryKeys.gql(REGIME_EPISODES_OPERATION, {}),
    queryFn: () => gql(RegimeEpisodesQuery, {}),
    select: (data): { episodes: readonly RegimeEpisode[]; recessions: readonly Recession[] } => ({
      episodes: data.regime?.episodes ?? [],
      recessions: data.regime?.recessions ?? [],
    }),
  });
}

/**
 * Stored market fields over `start..end` (`market.<group>@v<N>.<column>` names; the server cuts
 * `end` to the session): numbers as at most `points` points with gaps as null values, flags and
 * labels as segments. Waits until `end` is known; none when nothing is stored for the session.
 */
export function useMarketHistory(
  names: readonly string[],
  start: string,
  end: string | undefined,
  points: number,
) {
  const variables = { names: [...names], start, end: end ?? '', points };
  return useQuery({
    queryKey: queryKeys.gql(MARKET_HISTORY_OPERATION, variables),
    queryFn: () => gql(MarketHistoryQuery, variables),
    enabled: end !== undefined && names.length > 0,
    select: (data): readonly SeriesHistory[] => data.market?.history ?? [],
  });
}
