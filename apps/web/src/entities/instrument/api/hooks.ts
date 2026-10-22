/**
 * Read hooks for one instrument's detail pane over GraphQL (ADR 0037), by ticker or id, each
 * for the latest session: its stored events, its daily bars over a window, and its catalogue
 * features (values for the session and their recent history), asked in chunks the API's
 * `features(names)` cap allows.
 */
import {
  queryOptions,
  useQueries,
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryKey,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useMemo } from 'react';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

import type { ServedValue } from '@/entities/feature';

import { chunks, type FeatureHistory, type FeatureValues } from '../model/values';

/** The API's cap on `features(names)` / `series(names)` (graphql/limits.MAX_NAMES). */
export const NAMES_PER_REQUEST = 60;

const InstrumentEvents = graphql(`
  query InstrumentEvents($key: String!, $start: Date) {
    instrument(key: $key) {
      instrumentId
      events(start: $start) {
        table
        kind
        date
        ts
        values
      }
    }
  }
`);

/**
 * The stored calendar events (the API's default kinds: dividends, splits, earnings, ticker and
 * index changes) from `start` (ISO day; omitted: all time), so the chart asks no older than
 * its first day.
 */
export function useInstrumentEvents(key: string | null, start?: string) {
  const variables = start ? { key: key ?? '', start } : { key: key ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('InstrumentEvents', variables),
    queryFn: ({ queryKey }) => gql(InstrumentEvents, variables, queryKey),
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
    queryFn: ({ queryKey }) => gql(InstrumentPrices, variables, queryKey),
    select: (data: gqlTypes.InstrumentPricesQuery) => data.instrument?.prices.bars ?? [],
    enabled: Boolean(key),
    // Another range of the same instrument keeps the chart on screen while it loads.
    placeholderData: (previous, query) =>
      (query?.queryKey[2] as { key?: string } | undefined)?.key === key ? previous : undefined,
  });
}

/** `features(names)` is capped per field, so one request carries up to `SLOTS` aliased fields
 * (`f0`..`f9`, one chunk each): a catalogue-wide read is one operation, not one per chunk. */
const SLOTS = 10;

const InstrumentFeatureValues = graphql(`
  query InstrumentFeatureValues(
    $key: String!
    $date: Date
    $n0: [FeatureName!]!
    $n1: [FeatureName!]!
    $n2: [FeatureName!]!
    $n3: [FeatureName!]!
    $n4: [FeatureName!]!
    $n5: [FeatureName!]!
    $n6: [FeatureName!]!
    $n7: [FeatureName!]!
    $n8: [FeatureName!]!
    $n9: [FeatureName!]!
  ) {
    session(date: $date) {
      date
    }
    instrument(key: $key, date: $date) {
      instrumentId
      f0: features(names: $n0) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f1: features(names: $n1) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f2: features(names: $n2) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f3: features(names: $n3) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f4: features(names: $n4) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f5: features(names: $n5) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f6: features(names: $n6) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f7: features(names: $n7) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f8: features(names: $n8) {
        name
        value
        unknown {
          code
          reason
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
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      f9: features(names: $n9) {
        name
        value
        unknown {
          code
          reason
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

type ValuesQuery = gqlTypes.InstrumentFeatureValuesQuery;

/** The aliased `f0..` fields of an answer, in order. */
function servedOf(data: ValuesQuery | undefined): ServedValue[] {
  const instrument = data?.instrument as Record<string, unknown> | null | undefined;
  return Array.from(
    { length: SLOTS },
    (_, i) => instrument?.[`f${String(i)}`] ?? [],
  ).flat() as ServedValue[];
}

/** The variables of one request: `names` spread over the slots (the rest empty). */
function valuesVariables(key: string, date: string | null, names: readonly string[]) {
  const slots = chunks(names, NAMES_PER_REQUEST);
  const at = (i: number) => slots[i] ?? [];
  return {
    key,
    date,
    n0: at(0),
    n1: at(1),
    n2: at(2),
    n3: at(3),
    n4: at(4),
    n5: at(5),
    n6: at(6),
    n7: at(7),
    n8: at(8),
    n9: at(9),
  };
}

function valuesQuery(variables: ReturnType<typeof valuesVariables>) {
  return queryOptions({
    queryKey: queryKeys.gql('InstrumentFeatureValues', variables),
    queryFn: ({ queryKey }) => gql(InstrumentFeatureValues, variables, queryKey),
  });
}

/**
 * Start the first request of `useFeatureValues` (a route loader) and resolve to the session
 * it answered for (null: it failed); the hook joins it.
 */
export function prefetchFeatureValues(
  client: QueryClient,
  key: string,
  names: readonly string[],
): Promise<string | null> {
  const [first = []] = chunks(names, SLOTS * NAMES_PER_REQUEST);
  if (first.length === 0) return Promise.resolve(null);
  return client
    .query(valuesQuery(valuesVariables(key, null, first)))
    .then((data) => data.session?.date ?? null)
    .catch(() => null);
}

/**
 * The values of `names` (any catalogue features) for one session: one request for up to
 * `SLOTS` x `NAMES_PER_REQUEST` names. The first request resolves the latest session; a rarer
 * overflow asks for exactly that date (a publish between two requests never mixes sessions).
 */
export function useFeatureValues(key: string | null, names: readonly string[]): FeatureValues {
  const [first = [], ...rest] = chunks(names, SLOTS * NAMES_PER_REQUEST);
  const head = valuesVariables(key ?? '', null, first);
  const lead = useQuery({
    ...valuesQuery(head),
    enabled: Boolean(key) && first.length > 0,
  });
  const session = lead.data?.session?.date ?? null;
  return useQueries({
    queries: [
      {
        ...valuesQuery(head),
        enabled: Boolean(key) && first.length > 0,
      },
      ...rest.map((group) => {
        const variables = valuesVariables(key ?? '', session, group);
        return {
          queryKey: queryKeys.gql('InstrumentFeatureValues', variables),
          queryFn: ({ queryKey }: { queryKey: QueryKey }) =>
            gql(InstrumentFeatureValues, variables, queryKey),
          enabled: Boolean(key) && session !== null,
        };
      }),
    ],
    combine: combineValues,
  });
}

function combineValues(results: readonly UseQueryResult<ValuesQuery>[]): FeatureValues {
  return {
    session: results.find((r) => r.data)?.data?.session?.date ?? null,
    values: new Map(results.flatMap((r) => servedOf(r.data)).map((v) => [v.name, v] as const)),
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

function historyQuery(variables: { key: string; names: string[]; start: string; date: string }) {
  return queryOptions({
    queryKey: queryKeys.gql('InstrumentHistory', variables),
    queryFn: ({ queryKey }) => gql(InstrumentHistory, variables, queryKey),
  });
}

/** Start the first chunk of `useFeatureHistory` (a route loader); the hook joins it. */
export function prefetchFeatureHistory(
  client: QueryClient,
  key: string,
  names: readonly string[],
  start: string,
  date: string,
): void {
  const [chunk] = chunks(names, NAMES_PER_REQUEST);
  if (!chunk) return;
  void client.query(historyQuery({ key, names: chunk, start, date })).catch(() => undefined);
}

/**
 * Each of `names` (features with a history: not `instrument.*` facts) per session from
 * `start` to the session `date` (either null: not known yet, nothing is read), one request
 * per chunk. A history is a read per stored day of every table, so by default the first chunk
 * is read alone and the rest once it has settled. With `shown` (the names a table has on
 * screen) only the chunks holding a shown name are read, each when first shown (a long table
 * reads the history of the rows the reader reaches, not of every row).
 */
export function useFeatureHistory(
  key: string | null,
  names: readonly string[],
  start: string | null,
  date: string | null,
  shown?: ReadonlySet<string>,
): FeatureHistory {
  const client = useQueryClient();
  const ready = Boolean(key) && start !== null && date !== null;
  const keys = chunks(names, NAMES_PER_REQUEST).map((chunk) => {
    const variables = { key: key ?? '', names: chunk, start: start ?? '', date: date ?? '' };
    return { chunk, variables, queryKey: queryKeys.gql('InstrumentHistory', variables) };
  });
  const { series, isPending } = useQueries({
    queries: keys.map(({ chunk, variables, queryKey }, n) => {
      const first = n === 0 ? null : client.getQueryState(keys[0]?.queryKey ?? []);
      const wanted = shown
        ? chunk.some((name) => shown.has(name)) ||
          ['success', 'error'].includes(client.getQueryState(queryKey)?.status ?? '')
        : n === 0 || first?.status === 'success' || first?.status === 'error';
      return {
        ...historyQuery(variables),
        enabled: ready && wanted,
      };
    }),
    combine: combineHistory,
  });
  const pending = !ready || isPending;
  return useMemo(() => ({ series, isPending: pending }), [series, pending]);
}

function combineHistory(
  results: readonly UseQueryResult<gqlTypes.InstrumentHistoryQuery>[],
): FeatureHistory & { settled: number } {
  return {
    series: results.flatMap((r) => (r.data?.instrument ? [r.data.instrument.series] : [])),
    // a chunk not asked for (idle) is not pending: it waits for its turn or for its rows
    isPending: results.some((r) => r.isPending && r.fetchStatus !== 'idle'),
    // a chunk that fails changes no series: counted, so the hook re-renders to start the rest
    settled: results.filter((r) => r.isSuccess || r.isError).length,
  };
}
