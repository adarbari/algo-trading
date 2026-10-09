/**
 * The market regime reads (ADR 0047, ADR 0037): `Regime` is everything about the session's
 * regime but its history (label as weather, headline, scores, indicator cards with their
 * values, sizing) and `RegimeBands` the label history of a window as bands. Both go through the
 * one `Query.regime`; one `Regime` response is shared by every embedding (top bar, Ideas strip,
 * Regime page), so the cache key is the operation alone.
 */
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

import type { SeriesHistory } from '../model/history';
import type { Recession, Regime, RegimeBand, RegimeEpisode } from '../model/regime';
import type { EpisodeSignals } from '../model/signals';

/** The GraphQL operations' names: their cached responses share these key prefixes. */
export const REGIME_OPERATION = 'Regime';
export const REGIME_BANDS_OPERATION = 'RegimeBands';
export const REGIME_EPISODES_OPERATION = 'RegimeEpisodes';
export const REGIME_SIGNALS_OPERATION = 'RegimeSignals';
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
        kindText
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
            kindText
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
            kindText
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
            kindText
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
          kindText
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

const RegimeSignalsQuery = graphql(`
  query RegimeSignals {
    regime {
      episodes {
        key
        signals {
          gate {
            indicator
            kind
            state
            flaggedDay
            clearedDay
            flaggedDayFromTrough
            firstKnownDay
            neverFired
            unknownReason {
              code
              kind
              guideTerm
              kindText
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
          }
          indicators {
            indicator
            kind
            state
            flaggedDay
            clearedDay
            flaggedDayFromTrough
            firstKnownDay
            neverFired
            unknownReason {
              code
              kind
              guideTerm
              kindText
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
          }
        }
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
    ...regimeQuery(),
    select: (data): Regime | null => data.regime ?? null,
  });
}

const regimeQuery = () =>
  queryOptions({
    queryKey: queryKeys.gql(REGIME_OPERATION, {}),
    queryFn: () => gql(RegimeQuery, {}),
  });

/** Start reading the regime before the page opens (a link was hovered): a no-op while fresh. */
export function prefetchRegime(client: QueryClient): void {
  void client.query(regimeQuery()).catch(() => undefined);
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
 * When each indicator and the screener gate flagged and cleared around every reference episode,
 * as the session knew it (`Episode.signals`), by episode key (null: none for the session). One
 * request for the overview, which marks every episode; the History section asks, the Now and Why
 * sections never do.
 */
export function useRegimeSignals(enabled = true) {
  return useQuery({
    queryKey: queryKeys.gql(REGIME_SIGNALS_OPERATION, {}),
    queryFn: () => gql(RegimeSignalsQuery, {}),
    enabled,
    select: (data): ReadonlyMap<string, EpisodeSignals | null> =>
      new Map(
        (data.regime?.episodes ?? []).map((episode) => [episode.key, episode.signals ?? null]),
      ),
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
