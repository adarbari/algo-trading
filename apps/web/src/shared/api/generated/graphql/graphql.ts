/* eslint-disable */
/** Internal type. DO NOT USE DIRECTLY. */
type Exact<T extends { [key: string]: unknown }> = { [K in keyof T]: T[K] };
/** Internal type. DO NOT USE DIRECTLY. */
export type Incremental<T> = T | { [P in keyof T]?: P extends ' $fragmentName' | '__typename' ? T[P] : never };
import type { DocumentTypeDecoration } from '@graphql-typed-document-node/core';
/** How a client shows a feature's value */
export type FeatureFormat =
  | 'CATEGORY'
  | 'COMPACT'
  | 'CURRENCY'
  | 'DATE'
  | 'FLAG'
  | 'NUMBER'
  | 'PERCENT'
  | 'TEXT';

/** Why a value is UNKNOWN for the session */
export type UnknownCode =
  | 'LICENCE'
  | 'NOT_IN_CATALOGUE'
  | 'NOT_RUN'
  | 'NO_PARTITION'
  | 'NO_ROW'
  | 'NULL'
  | 'PRE_SNAPSHOT';

export type OptionChainQueryVariables = Exact<{
  key: string;
  names: Array<string> | string;
}>;


export type OptionChainQuery = { instrument: { instrumentId: string, symbol: string, features: Array<{ name: string, value: unknown, unknown: { code: UnknownCode, detail: string } | null, info: { format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string } }>, chain: { underlyingId: string, session: string, status: string | null, strikes: Array<number>, expiries: Array<{ date: string, days: number }> } | null } | null };

export type OptionQuotesQueryVariables = Exact<{
  key: string;
  expiry: string;
  date: string;
}>;


export type OptionQuotesQuery = { instrument: { instrumentId: string, chain: { quotes: Array<{ instrumentId: string, expiry: string, right: string, strike: number, bid: number | null, ask: number | null, last: number | null, volume: number | null, openInterest: number | null, iv: number | null, delta: number | null, gamma: number | null, theta: number | null, vega: number | null }> } | null } | null };

export type EtfHoldingsQueryVariables = Exact<{
  key: string;
  top: number;
}>;


export type EtfHoldingsQuery = { instrument: { instrumentId: string, isEtf: boolean, holdings: { asOf: string | null, source: string | null, total: number, items: Array<{ rank: number, name: string, symbol: string | null, weight: number, assetClass: string | null, instrument: { symbol: string } | null }> } | null } | null };

export type InstrumentFactsQueryVariables = Exact<{
  key: string;
  names: Array<string> | string;
}>;


export type InstrumentFactsQuery = { session: { date: string, isLatest: boolean, missing: Array<string>, referenceSnapshot: string | null, preSnapshot: boolean } | null, instrument: { instrumentId: string, symbol: string, name: string, securityType: string | null, exchange: string | null, isEtf: boolean, description: string | null, referenceSnapshot: string, features: Array<{ name: string, value: unknown, unknown: { code: UnknownCode, detail: string } | null, info: { format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string } }> } | null };

export type InstrumentEventsQueryVariables = Exact<{
  key: string;
}>;


export type InstrumentEventsQuery = { instrument: { instrumentId: string, events: Array<{ table: string, kind: string, date: string, ts: string, values: unknown }> } | null };

export type InstrumentPricesQueryVariables = Exact<{
  key: string;
  start: string;
}>;


export type InstrumentPricesQuery = { instrument: { instrumentId: string, prices: { start: string, end: string, bars: Array<{ session: string, close: number, volume: number }> } } | null };

export type InstrumentFeatureValuesQueryVariables = Exact<{
  key: string;
  names: Array<string> | string;
  date?: string | null | undefined;
}>;


export type InstrumentFeatureValuesQuery = { session: { date: string } | null, instrument: { instrumentId: string, features: Array<{ name: string, value: unknown, unknown: { code: UnknownCode, detail: string } | null, info: { format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string } }> } | null };

export type InstrumentHistoryQueryVariables = Exact<{
  key: string;
  names: Array<string> | string;
  start: string;
  date: string;
}>;


export type InstrumentHistoryQuery = { instrument: { instrumentId: string, series: { names: Array<string>, points: Array<{ session: string, values: Array<unknown> }> } } | null };

export class TypedDocumentString<TResult, TVariables>
  extends String
  implements DocumentTypeDecoration<TResult, TVariables>
{
  __apiType?: NonNullable<DocumentTypeDecoration<TResult, TVariables>['__apiType']>;
  private value: string;
  public __meta__?: Record<string, any> | undefined;

  constructor(value: string, __meta__?: Record<string, any> | undefined) {
    super(value);
    this.value = value;
    this.__meta__ = __meta__;
  }

  override toString(): string & DocumentTypeDecoration<TResult, TVariables> {
    return this.value;
  }
}

export const OptionChainDocument = new TypedDocumentString(`
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
    `) as unknown as TypedDocumentString<OptionChainQuery, OptionChainQueryVariables>;
export const OptionQuotesDocument = new TypedDocumentString(`
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
    `) as unknown as TypedDocumentString<OptionQuotesQuery, OptionQuotesQueryVariables>;
export const EtfHoldingsDocument = new TypedDocumentString(`
    query EtfHoldings($key: String!, $top: Int!) {
  instrument(key: $key) {
    instrumentId
    isEtf
    holdings(top: $top) {
      asOf
      source
      total
      items {
        rank
        name
        symbol
        weight
        assetClass
        instrument {
          symbol
        }
      }
    }
  }
}
    `) as unknown as TypedDocumentString<EtfHoldingsQuery, EtfHoldingsQueryVariables>;
export const InstrumentFactsDocument = new TypedDocumentString(`
    query InstrumentFacts($key: String!, $names: [FeatureName!]!) {
  session {
    date
    isLatest
    missing
    referenceSnapshot
    preSnapshot
  }
  instrument(key: $key) {
    instrumentId
    symbol
    name
    securityType
    exchange
    isEtf
    description
    referenceSnapshot
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
  }
}
    `) as unknown as TypedDocumentString<InstrumentFactsQuery, InstrumentFactsQueryVariables>;
export const InstrumentEventsDocument = new TypedDocumentString(`
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
    `) as unknown as TypedDocumentString<InstrumentEventsQuery, InstrumentEventsQueryVariables>;
export const InstrumentPricesDocument = new TypedDocumentString(`
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
    `) as unknown as TypedDocumentString<InstrumentPricesQuery, InstrumentPricesQueryVariables>;
export const InstrumentFeatureValuesDocument = new TypedDocumentString(`
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
    `) as unknown as TypedDocumentString<InstrumentFeatureValuesQuery, InstrumentFeatureValuesQueryVariables>;
export const InstrumentHistoryDocument = new TypedDocumentString(`
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
    `) as unknown as TypedDocumentString<InstrumentHistoryQuery, InstrumentHistoryQueryVariables>;