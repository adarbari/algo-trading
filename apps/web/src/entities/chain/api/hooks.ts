/**
 * Read hooks for an underlying's option chain over GraphQL (ADR 0037), for the latest
 * session: the chain (expiries with their days, strikes, status) with the per-instrument
 * facts the Options view shows (catalogue features: the target expiry, the underlying's
 * price with the chain, our IV30), and the quotes of one expiry.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys, type gqlTypes } from '@/shared/api';

import { CHAIN_FEATURES } from '../model/chain';

const OptionChain = graphql(`
  query OptionChain($key: String!, $names: [FeatureName!]!) {
    instrument(key: $key) {
      instrumentId
      symbol
      features(names: $names) {
        name
        value
        unknown {
          code
          detail
        }
        info {
          format
          unit
          dtype
          nullMeaning
        }
      }
      chain {
        underlyingId
        session
        status
        expiries {
          date
          days
        }
        strikes
      }
    }
  }
`);

/** The chain stored for the session with its facts (`instrument` null: no such ticker). */
export function useOptionChain(key: string | null) {
  const variables = { key: key ?? '', names: [...CHAIN_FEATURES] };
  return useQuery({
    queryKey: queryKeys.gql('OptionChain', variables),
    queryFn: () => gql(OptionChain, variables),
    select: (data: gqlTypes.OptionChainQuery) => data.instrument,
    enabled: Boolean(key),
  });
}

const OptionQuotes = graphql(`
  query OptionQuotes($key: String!, $expiry: Date!, $date: Date!) {
    instrument(key: $key, date: $date) {
      instrumentId
      chain {
        quotes(expiry: $expiry) {
          instrumentId
          expiry
          right
          strike
          bid
          ask
          last
          volume
          openInterest
          iv
          delta
          gamma
          theta
          vega
        }
      }
    }
  }
`);

/** The stored quotes of one expiry of the chain of `session` (the session `useOptionChain`
 * answered for, so a publish in between never mixes days; null: nothing is read yet). */
export function useOptionQuotes(key: string | null, expiry: string | null, session: string | null) {
  const variables = { key: key ?? '', expiry: expiry ?? '', date: session ?? '' };
  return useQuery({
    queryKey: queryKeys.gql('OptionQuotes', variables),
    queryFn: () => gql(OptionQuotes, variables),
    select: (data: gqlTypes.OptionQuotesQuery) => data.instrument?.chain?.quotes ?? [],
    enabled: Boolean(key) && expiry !== null && session !== null,
    // Another expiry of the same underlying keeps the table on screen while it loads.
    placeholderData: (previous, query) =>
      (query?.queryKey[2] as { key?: string } | undefined)?.key === key ? previous : undefined,
  });
}
