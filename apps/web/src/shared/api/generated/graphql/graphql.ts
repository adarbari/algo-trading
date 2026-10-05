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

export type FeatureCatalogueQueryVariables = Exact<{ [key: string]: never; }>;


export type FeatureCatalogueQuery = { catalogue: Array<{ name: string, kind: string, source: string, dtype: string, format: FeatureFormat, description: string, nullMeaning: string, version: number | null, group: string | null, key: string | null, inputs: Array<string>, unit: string | null, range: Array<number | null> | null, categories: Array<string>, scope: string, owner: string | null, licence: string }> };

export type FeatureDistributionQueryVariables = Exact<{
  name: string;
}>;


export type FeatureDistributionQuery = { distribution: { name: string, session: string, count: number, nulls: number, quantiles: Array<{ q: number, value: number }>, histogram: Array<{ lo: number, hi: number, count: number }>, categories: Array<{ value: string, count: number }>, unknown: { code: UnknownCode, detail: string } | null } | null };

export type InstrumentFactsQueryVariables = Exact<{
  key: string;
  names: Array<string> | string;
}>;


export type InstrumentFactsQuery = { session: { date: string, isLatest: boolean, missing: Array<string>, referenceSnapshot: string | null, preSnapshot: boolean } | null, instrument: { instrumentId: string, symbol: string, name: string, securityType: string | null, exchange: string | null, isEtf: boolean, description: string | null, referenceSnapshot: string, features: Array<{ name: string, value: unknown, unknown: { code: UnknownCode, detail: string } | null, info: { format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string } }> } | null };

export type ScreenerConfigsQueryVariables = Exact<{ [key: string]: never; }>;


export type ScreenerConfigsQuery = { configs: Array<{ configId: string, scope: string, kind: string | null, impl: string | null, selection: string | null, hash: string | null, error: string | null }> };

export type MyScreensQueryVariables = Exact<{ [key: string]: never; }>;


export type MyScreensQuery = { myScreens: Array<{ screenerId: string, status: string, latest: number | null, hasDraft: boolean, presetId: string | null }> };

export type ScreenDetailQueryVariables = Exact<{
  id: string;
}>;


export type ScreenDetailQuery = { screenDetail: { screenerId: string, user: string, draft: unknown, draftError: string | null, versions: Array<number>, latest: number | null, hash: string | null, layers: Array<string>, resolved: unknown, error: string | null, working: unknown, preset: { presetId: string, pinned: number | null, current: number | null, rebaseAvailable: boolean } | null } | null };

export type ScreenVersionsQueryVariables = Exact<{
  id: string;
}>;


export type ScreenVersionsQuery = { screenVersions: Array<{ version: number, document: unknown }> };

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

export const FeatureCatalogueDocument = new TypedDocumentString(`
    query FeatureCatalogue {
  catalogue {
    name
    kind
    source
    dtype
    format
    description
    nullMeaning
    version
    group
    key
    inputs
    unit
    range
    categories
    scope
    owner
    licence
  }
}
    `) as unknown as TypedDocumentString<FeatureCatalogueQuery, FeatureCatalogueQueryVariables>;
export const FeatureDistributionDocument = new TypedDocumentString(`
    query FeatureDistribution($name: FeatureName!) {
  distribution(name: $name) {
    name
    session
    count
    nulls
    quantiles {
      q
      value
    }
    histogram {
      lo
      hi
      count
    }
    categories {
      value
      count
    }
    unknown {
      code
      detail
    }
  }
}
    `) as unknown as TypedDocumentString<FeatureDistributionQuery, FeatureDistributionQueryVariables>;
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
export const ScreenerConfigsDocument = new TypedDocumentString(`
    query ScreenerConfigs {
  configs(kind: "screener") {
    configId
    scope
    kind
    impl
    selection
    hash
    error
  }
}
    `) as unknown as TypedDocumentString<ScreenerConfigsQuery, ScreenerConfigsQueryVariables>;
export const MyScreensDocument = new TypedDocumentString(`
    query MyScreens {
  myScreens {
    screenerId
    status
    latest
    hasDraft
    presetId
  }
}
    `) as unknown as TypedDocumentString<MyScreensQuery, MyScreensQueryVariables>;
export const ScreenDetailDocument = new TypedDocumentString(`
    query ScreenDetail($id: String!) {
  screenDetail(screenerId: $id) {
    screenerId
    user
    draft
    draftError
    versions
    latest
    preset {
      presetId
      pinned
      current
      rebaseAvailable
    }
    hash
    layers
    resolved
    error
    working
  }
}
    `) as unknown as TypedDocumentString<ScreenDetailQuery, ScreenDetailQueryVariables>;
export const ScreenVersionsDocument = new TypedDocumentString(`
    query ScreenVersions($id: String!) {
  screenVersions(screenerId: $id) {
    version
    document
  }
}
    `) as unknown as TypedDocumentString<ScreenVersionsQuery, ScreenVersionsQueryVariables>;