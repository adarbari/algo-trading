/**
 * Read hooks for one instrument's detail pane over GraphQL (ADR 0037), by ticker or id, each
 * for the latest session: its stored events, its daily bars over a window, and its catalogue
 * features (values for the session and their recent history), asked in chunks the API's
 * `features(names)` cap allows.
 */
import { useQueries, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

import { chunks, type FeatureHistory, type FeatureValues } from '../model/values';

/** The API's cap on `features(names)` / `series(names)` (graphql/limits.MAX_NAMES). */
export const NAMES_PER_REQUEST = 60;

const InstrumentEvents = graphql(`
  query InstrumentEvents($key: String!) {
    instrument(key: $key) {
      instrumentId
      events {
        table
        kind
        date
        ts
        values
      }
    }
  }
`);

/** Every stored event (all time): dividends, splits, earnings, ticker and index changes. */
export function useInstrumentEvents(key: string | null) {
  const variables = { key: key ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentEvents', variables),
    queryFn: () => gql(InstrumentEvents, variables),
    select: (data: gqlTypes.InstrumentEventsQuery) => data.instrument?.events ?? [],
    enabled: Boolean(key),
  });
}

const InstrumentPrices = graphql(`
  query InstrumentPrices($key: String!, $start: Date!) {
    instrument(key: $key) {
      instrumentId
      prices(start: $start) {
        start
        end
        bars {
          session
          close
          volume
        }
      }
    }
  }
`);

/** Split-adjusted daily bars from `start` to the session. */
export function useInstrumentPrices(key: string | null, start: string) {
  const variables = { key: key ?? '', start };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentPrices', variables),
    queryFn: () => gql(InstrumentPrices, variables),
    select: (data: gqlTypes.InstrumentPricesQuery) => data.instrument?.prices.bars ?? [],
    enabled: Boolean(key),
    // Another range of the same instrument keeps the chart on screen while it loads.
    placeholderData: (previous, query) =>
      (query?.queryKey[2] as { key?: string } | undefined)?.key === key ? previous : undefined,
  });
}

const InstrumentFeatureValues = graphql(`
  query InstrumentFeatureValues($key: String!, $names: [FeatureName!]!, $date: Date) {
    session(date: $date) {
      date
    }
    instrument(key: $key, date: $date) {
      instrumentId
      features(names: $names) {
        name
        value
        unknown {
          code
          detail
          reason
        }
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
    }
  }
`);

/**
 * The values of `names` (any catalogue features) for one session, one request per chunk: the
 * first chunk resolves the latest session, the others ask for exactly that date (a publish
 * between two requests never mixes sessions).
 */
export function useFeatureValues(key: string | null, names: readonly string[]): FeatureValues {
  const [first = [], ...rest] = chunks(names, NAMES_PER_REQUEST);
  const head = { key: key ?? '', names: first, date: null };
  const lead = useQuery({
    queryKey: queryKeys.gql('InstrumentFeatureValues', head),
    queryFn: () => gql(InstrumentFeatureValues, head),
    enabled: Boolean(key) && first.length > 0,
  });
  const session = lead.data?.session?.date ?? null;
  return useQueries({
    queries: [
      {
        queryKey: queryKeys.gql('InstrumentFeatureValues', head),
        queryFn: () => gql(InstrumentFeatureValues, head),
        enabled: Boolean(key) && first.length > 0,
      },
      ...rest.map((chunk) => {
        const variables = { key: key ?? '', names: chunk, date: session };
        return {
          queryKey: queryKeys.gql('InstrumentFeatureValues', variables),
          queryFn: () => gql(InstrumentFeatureValues, variables),
          enabled: Boolean(key) && session !== null,
        };
      }),
    ],
    combine: combineValues,
  });
}

function combineValues(
  results: readonly UseQueryResult<gqlTypes.InstrumentFeatureValuesQuery>[],
): FeatureValues {
  return {
    session: results.find((r) => r.data)?.data?.session?.date ?? null,
    values: new Map(
      results.flatMap((r) => r.data?.instrument?.features ?? []).map((v) => [v.name, v]),
    ),
    isPending: results.some((r) => r.isPending),
    isError: results.some((r) => r.isError),
    refetch: () => Promise.all(results.map((r) => r.refetch())),
  };
}

const InstrumentHistory = graphql(`
  query InstrumentHistory($key: String!, $names: [FeatureName!]!, $start: Date!, $date: Date!) {
    instrument(key: $key, date: $date) {
      instrumentId
      series(names: $names, start: $start) {
        names
        points {
          session
          values
        }
      }
    }
  }
`);

/**
 * Each of `names` (features with a history: not `instrument.*` facts) per session from
 * `start` to the session `date` (either null: not known yet, nothing is read), one request
 * per chunk.
 */
export function useFeatureHistory(
  key: string | null,
  names: readonly string[],
  start: string | null,
  date: string | null,
): FeatureHistory {
  return useQueries({
    queries: chunks(names, NAMES_PER_REQUEST).map((chunk) => {
      const variables = { key: key ?? '', names: chunk, start: start ?? '', date: date ?? '' };
      return {
        queryKey: queryKeys.gql('InstrumentHistory', variables),
        queryFn: () => gql(InstrumentHistory, variables),
        enabled: Boolean(key) && start !== null && date !== null,
      };
    }),
    combine: combineHistory,
  });
}

function combineHistory(
  results: readonly UseQueryResult<gqlTypes.InstrumentHistoryQuery>[],
): FeatureHistory {
  return {
    series: results.flatMap((r) => (r.data?.instrument ? [r.data.instrument.series] : [])),
    isPending: results.some((r) => r.isPending),
  };
}
