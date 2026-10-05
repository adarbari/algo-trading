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

export type IdeasPageQueryVariables = Exact<{
  limit: number;
  names: Array<string> | string;
}>;


export type IdeasPageQuery = { ideas: { session: string, priority: Array<string>, total: number, screeners: Array<{ picked: number, screener: { id: string, name: string, owner: string, version: number | null }, run: { runId: string, configVersion: number | null } | null, notRun: { code: UnknownCode, detail: string } | null, top: Array<{ instrumentId: string, score: number | null, instrument: { symbol: string } | null }> }>, items: Array<{ rank: number, instrumentId: string, instrument: { symbol: string, features: Array<{ name: string, value: unknown, unknown: { code: UnknownCode, detail: string } | null, info: { format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string } }> } | null, picks: Array<{ configId: string, decision: string, score: number | null, reasons: string, flags: Array<string>, criteria: Array<{ id: string, value: unknown }>, columns: Array<{ name: string, value: unknown }> }> }> } | null };

export type InstrumentFactsQueryVariables = Exact<{
  key: string;
  names: Array<string> | string;
}>;


export type InstrumentFactsQuery = { session: { date: string, isLatest: boolean, missing: Array<string>, referenceSnapshot: string | null, preSnapshot: boolean } | null, instrument: { instrumentId: string, symbol: string, name: string, securityType: string | null, exchange: string | null, isEtf: boolean, description: string | null, referenceSnapshot: string, features: Array<{ name: string, value: unknown, unknown: { code: UnknownCode, detail: string } | null, info: { format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string } }> } | null };

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

export const IdeasPageDocument = new TypedDocumentString(`
    query IdeasPage($limit: Int!, $names: [FeatureName!]!) {
  ideas(limit: $limit) {
    session
    priority
    total
    screeners {
      screener {
        id
        name
        owner
        version
      }
      run {
        runId
        configVersion
      }
      notRun {
        code
        detail
      }
      picked
      top {
        instrumentId
        score
        instrument {
          symbol
        }
      }
    }
    items {
      rank
      instrumentId
      instrument {
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
      }
      picks {
        configId
        decision
        score
        reasons
        flags
        criteria {
          id
          value
        }
        columns {
          name
          value
        }
      }
    }
  }
}
    `) as unknown as TypedDocumentString<IdeasPageQuery, IdeasPageQueryVariables>;
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