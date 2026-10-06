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

export type ComparePricesQueryVariables = Exact<{
  keys: Array<string> | string;
  start: string;
}>;


export type ComparePricesQuery = { table: { instruments: Array<{ instrumentId: string, symbol: string, prices: { bars: Array<{ session: string, close: number }> } }> } | null };

export type FeatureCatalogueQueryVariables = Exact<{ [key: string]: never; }>;


export type FeatureCatalogueQuery = { catalogue: Array<{ name: string, kind: string, source: string, dtype: string, format: FeatureFormat, description: string, nullMeaning: string, version: number | null, group: string | null, key: string | null, inputs: Array<string>, unit: string | null, range: Array<number | null> | null, categories: Array<string>, scope: string, owner: string | null, licence: string }> };

export type FeatureDistributionQueryVariables = Exact<{
  name: string;
}>;


export type FeatureDistributionQuery = { distribution: { name: string, session: string, count: number, nulls: number, quantiles: Array<{ q: number, value: number }>, histogram: Array<{ lo: number, hi: number, count: number }>, categories: Array<{ value: string, count: number }>, unknown: { code: UnknownCode, detail: string } | null } | null };

export type FeatureTableQueryVariables = Exact<{
  columns: Array<string> | string;
  keys?: Array<string> | string | null | undefined;
  securityType?: string | null | undefined;
  sector?: string | null | undefined;
  liquidityClass?: string | null | undefined;
  leveraged?: boolean | null | undefined;
  optionable?: boolean | null | undefined;
  q?: string | null | undefined;
  sort?: string | null | undefined;
  page?: number | null | undefined;
  size?: number | null | undefined;
}>;


export type FeatureTableQuery = { table: { universeSnapshot: string | null, preSnapshot: boolean, sort: string | null, total: number, page: number, size: number, missing: Array<string>, rows: Array<Array<unknown>>, unknown: Array<Array<UnknownCode | null>>, session: { date: string, missing: Array<string> }, columns: Array<{ name: string, description: string, format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string, licence: string, scope: string }>, instruments: Array<{ instrumentId: string, symbol: string, name: string }> } | null };

export type EtfHoldingsQueryVariables = Exact<{
  key: string;
  top: number;
}>;


export type EtfHoldingsQuery = { instrument: { instrumentId: string, isEtf: boolean, holdings: { asOf: string | null, source: string | null, total: number, items: Array<{ rank: number, name: string, symbol: string | null, weight: number, assetClass: string | null, instrument: { symbol: string } | null }> } | null } | null };

export type IdeasPageQueryVariables = Exact<{
  limit: number;
  names: Array<string> | string;
}>;


export type IdeasPageQuery = { ideas: { session: string, priority: Array<string>, total: number, screeners: Array<{ picked: number, screener: { id: string, name: string, owner: string, version: number | null }, run: { runId: string, configVersion: number | null } | null, notRun: { code: UnknownCode, detail: string } | null, top: Array<{ instrumentId: string, score: number | null, instrument: { symbol: string } | null }> }>, items: Array<{ rank: number, instrumentId: string, instrument: { symbol: string, features: Array<{ name: string, value: unknown, unknown: { code: UnknownCode, detail: string } | null, info: { format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string } }> } | null, picks: Array<{ configId: string, decision: string, score: number | null, reasons: string, flags: Array<string>, criteria: Array<{ id: string, value: unknown }>, columns: Array<{ name: string, value: unknown }> }> }> } | null };

export type IngestionCompletenessQueryVariables = Exact<{
  sessions: number;
}>;


export type IngestionCompletenessQuery = { completeness: { sessions: Array<string>, datasets: Array<string>, lastClosed: string, cells: Array<{ dataset: string, session: string, status: string, present: number, expected: number | null, basis: string, runIds: Array<string> }> } | null };

export type IngestionCellQueryVariables = Exact<{
  dataset: string;
  date: string;
}>;


export type IngestionCellQuery = { ingestionCell: { job: string, cell: { dataset: string, session: string, status: string, present: number, expected: number | null, basis: string, runIds: Array<string> }, groups: Array<{ reason: string, count: number, examples: Array<string>, statuses: Array<string> }>, runs: Array<{ runId: string, job: string, session: string, status: string, startedAt: string, finishedAt: string | null, durationS: number | null, itemsTotal: number, itemsByStatus: unknown, stats: unknown, failures: Array<{ reason: string, count: number, examples: Array<string>, statuses: Array<string> }> }> } | null };

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

export type FigiReviewQueryVariables = Exact<{ [key: string]: never; }>;


export type FigiReviewQuery = { figiReview: { session: string | null, source: string, items: Array<unknown> } | null };

export type LeverageReviewQueryVariables = Exact<{ [key: string]: never; }>;


export type LeverageReviewQuery = { leverageReview: { session: string | null, source: string, items: Array<unknown> } | null };

export type NightlyRunsQueryVariables = Exact<{
  limit: number;
}>;


export type NightlyRunsQuery = { nightlyRuns: Array<{ runId: string, session: string, status: string, startedAt: string, finishedAt: string | null, durationS: number | null, problems: Array<string>, steps: Array<{ name: string, status: string, durationS: number | null, reason: string | null, error: string | null }> }> };

export type RunRecordQueryVariables = Exact<{
  runId: string;
}>;


export type RunRecordQuery = { run: { runId: string, job: string, session: string, status: string, startedAt: string, finishedAt: string | null, durationS: number | null, itemsTotal: number, itemsByStatus: unknown, stats: unknown, failures: Array<{ reason: string, count: number, examples: Array<string>, statuses: Array<string> }> } | null };

export type RunItemsQueryVariables = Exact<{
  runId: string;
}>;


export type RunItemsQuery = { runItems: Array<{ key: string, code: string, status: string }> | null };

export type QualityChecksQueryVariables = Exact<{ [key: string]: never; }>;


export type QualityChecksQuery = { quality: { session: string, runId: string | null, status: string | null, finishedAt: string | null, checks: Array<{ name: string, status: string, detail: string }>, unknown: { code: UnknownCode, detail: string } | null } | null };

export type InstrumentScreenerHitsQueryVariables = Exact<{
  key: string;
}>;


export type InstrumentScreenerHitsQuery = { session: { date: string } | null, instrument: { instrumentId: string, symbol: string, screenerHits: Array<{ screener: { id: string, name: string }, result: { rank: number, decision: string, score: number | null, reasons: string, flags: Array<string>, change: string | null } }> } | null };

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

export type ScreenerResultsQueryVariables = Exact<{
  id: string;
  decisions?: Array<string> | string | null | undefined;
  change?: string | null | undefined;
  q?: string | null | undefined;
  sort?: string | null | undefined;
  columns?: Array<string> | string | null | undefined;
  page?: number | null | undefined;
  size?: number | null | undefined;
}>;


export type ScreenerResultsQuery = { session: { date: string, missing: Array<string> } | null, screener: { id: string, name: string, criteria: Array<{ id: string, field: string, mode: string }>, displayColumns: Array<{ name: string, field: string }>, notRun: { code: UnknownCode, detail: string } | null, latestRun: { runId: string, session: string, previousSession: string | null, decisions: Array<{ decision: string, count: number }>, changes: Array<{ change: string, count: number }>, results: { sort: string, total: number, page: number, size: number, missing: Array<string>, rows: Array<Array<unknown>>, unknown: Array<Array<UnknownCode | null>>, columns: Array<{ name: string, description: string, format: FeatureFormat, unit: string | null, dtype: string, nullMeaning: string, licence: string, scope: string }>, results: Array<{ instrumentId: string, rank: number, decision: string, score: number | null, reasons: string, flags: Array<string>, change: string | null, previousDecision: string | null, instrument: { instrumentId: string, symbol: string, name: string } | null, criteria: Array<{ id: string, field: string, mode: string, outcome: string, value: unknown, distance: number | null }>, columns: Array<{ name: string, value: unknown }> }> } } | null } | null };

export type VerificationQueryVariables = Exact<{ [key: string]: never; }>;


export type VerificationQuery = { verification: { session: string, runIds: Array<string>, instruments: number, counts: unknown, failing: Array<unknown>, byCheck: Array<{ check: string, counts: unknown }>, unknown: { code: UnknownCode, detail: string } | null } | null };

export type ViewerQueryVariables = Exact<{ [key: string]: never; }>;


export type ViewerQuery = { viewer: { id: string, name: string, role: string, workspaces: Array<string> } };

export type TableViewQueryVariables = Exact<{
  scope: string;
  name?: string | null | undefined;
}>;


export type TableViewQuery = { view: { scope: string, name: string | null, saved: boolean, columns: Array<string>, sort: string | null, decisions: Array<string>, names: Array<string> } | null };

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
export const ComparePricesDocument = new TypedDocumentString(`
    query ComparePrices($keys: [String!]!, $start: Date!) {
  table(columns: [], keys: $keys) {
    instruments {
      instrumentId
      symbol
      prices(start: $start) {
        bars {
          session
          close
        }
      }
    }
  }
}
    `) as unknown as TypedDocumentString<ComparePricesQuery, ComparePricesQueryVariables>;
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
export const FeatureTableDocument = new TypedDocumentString(`
    query FeatureTable($columns: [FeatureName!]!, $keys: [String!], $securityType: String, $sector: String, $liquidityClass: String, $leveraged: Boolean, $optionable: Boolean, $q: String, $sort: String, $page: Int, $size: Int) {
  table(
    columns: $columns
    keys: $keys
    securityType: $securityType
    sector: $sector
    liquidityClass: $liquidityClass
    leveraged: $leveraged
    optionable: $optionable
    q: $q
    sort: $sort
    page: $page
    size: $size
  ) {
    session {
      date
      missing
    }
    universeSnapshot
    preSnapshot
    sort
    total
    page
    size
    missing
    columns {
      name
      description
      format
      unit
      dtype
      nullMeaning
      licence
      scope
    }
    instruments {
      instrumentId
      symbol
      name
    }
    rows
    unknown
  }
}
    `) as unknown as TypedDocumentString<FeatureTableQuery, FeatureTableQueryVariables>;
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
export const IngestionCompletenessDocument = new TypedDocumentString(`
    query IngestionCompleteness($sessions: Int!) {
  completeness(sessions: $sessions) {
    sessions
    datasets
    lastClosed
    cells {
      dataset
      session
      status
      present
      expected
      basis
      runIds
    }
  }
}
    `) as unknown as TypedDocumentString<IngestionCompletenessQuery, IngestionCompletenessQueryVariables>;
export const IngestionCellDocument = new TypedDocumentString(`
    query IngestionCell($dataset: String!, $date: Date!) {
  ingestionCell(dataset: $dataset, date: $date) {
    job
    cell {
      dataset
      session
      status
      present
      expected
      basis
      runIds
    }
    groups {
      reason
      count
      examples
      statuses
    }
    runs {
      runId
      job
      session
      status
      startedAt
      finishedAt
      durationS
      itemsTotal
      itemsByStatus
      stats
      failures {
        reason
        count
        examples
        statuses
      }
    }
  }
}
    `) as unknown as TypedDocumentString<IngestionCellQuery, IngestionCellQueryVariables>;
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
export const FigiReviewDocument = new TypedDocumentString(`
    query FigiReview {
  figiReview {
    session
    source
    items
  }
}
    `) as unknown as TypedDocumentString<FigiReviewQuery, FigiReviewQueryVariables>;
export const LeverageReviewDocument = new TypedDocumentString(`
    query LeverageReview {
  leverageReview {
    session
    source
    items
  }
}
    `) as unknown as TypedDocumentString<LeverageReviewQuery, LeverageReviewQueryVariables>;
export const NightlyRunsDocument = new TypedDocumentString(`
    query NightlyRuns($limit: Int!) {
  nightlyRuns(limit: $limit) {
    runId
    session
    status
    startedAt
    finishedAt
    durationS
    problems
    steps {
      name
      status
      durationS
      reason
      error
    }
  }
}
    `) as unknown as TypedDocumentString<NightlyRunsQuery, NightlyRunsQueryVariables>;
export const RunRecordDocument = new TypedDocumentString(`
    query RunRecord($runId: String!) {
  run(runId: $runId) {
    runId
    job
    session
    status
    startedAt
    finishedAt
    durationS
    itemsTotal
    itemsByStatus
    stats
    failures {
      reason
      count
      examples
      statuses
    }
  }
}
    `) as unknown as TypedDocumentString<RunRecordQuery, RunRecordQueryVariables>;
export const RunItemsDocument = new TypedDocumentString(`
    query RunItems($runId: String!) {
  runItems(runId: $runId) {
    key
    code
    status
  }
}
    `) as unknown as TypedDocumentString<RunItemsQuery, RunItemsQueryVariables>;
export const QualityChecksDocument = new TypedDocumentString(`
    query QualityChecks {
  quality {
    session
    runId
    status
    finishedAt
    checks {
      name
      status
      detail
    }
    unknown {
      code
      detail
    }
  }
}
    `) as unknown as TypedDocumentString<QualityChecksQuery, QualityChecksQueryVariables>;
export const InstrumentScreenerHitsDocument = new TypedDocumentString(`
    query InstrumentScreenerHits($key: String!) {
  session {
    date
  }
  instrument(key: $key) {
    instrumentId
    symbol
    screenerHits {
      screener {
        id
        name
      }
      result {
        rank
        decision
        score
        reasons
        flags
        change
      }
    }
  }
}
    `) as unknown as TypedDocumentString<InstrumentScreenerHitsQuery, InstrumentScreenerHitsQueryVariables>;
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
export const ScreenerResultsDocument = new TypedDocumentString(`
    query ScreenerResults($id: String!, $decisions: [String!], $change: String, $q: String, $sort: String, $columns: [FeatureName!], $page: Int, $size: Int) {
  session {
    date
    missing
  }
  screener(id: $id) {
    id
    name
    criteria {
      id
      field
      mode
    }
    displayColumns {
      name
      field
    }
    notRun {
      code
      detail
    }
    latestRun {
      runId
      session
      previousSession
      decisions {
        decision
        count
      }
      changes {
        change
        count
      }
      results(
        decisions: $decisions
        change: $change
        q: $q
        sort: $sort
        columns: $columns
        page: $page
        size: $size
      ) {
        sort
        total
        page
        size
        missing
        columns {
          name
          description
          format
          unit
          dtype
          nullMeaning
          licence
          scope
        }
        rows
        unknown
        results {
          instrumentId
          rank
          decision
          score
          reasons
          flags
          change
          previousDecision
          instrument {
            instrumentId
            symbol
            name
          }
          criteria {
            id
            field
            mode
            outcome
            value
            distance
          }
          columns {
            name
            value
          }
        }
      }
    }
  }
}
    `) as unknown as TypedDocumentString<ScreenerResultsQuery, ScreenerResultsQueryVariables>;
export const VerificationDocument = new TypedDocumentString(`
    query Verification {
  verification {
    session
    runIds
    instruments
    counts
    byCheck {
      check
      counts
    }
    failing
    unknown {
      code
      detail
    }
  }
}
    `) as unknown as TypedDocumentString<VerificationQuery, VerificationQueryVariables>;
export const ViewerDocument = new TypedDocumentString(`
    query Viewer {
  viewer {
    id
    name
    role
    workspaces
  }
}
    `) as unknown as TypedDocumentString<ViewerQuery, ViewerQueryVariables>;
export const TableViewDocument = new TypedDocumentString(`
    query TableView($scope: String!, $name: String) {
  view(scope: $scope, name: $name) {
    scope
    name
    saved
    columns
    sort
    decisions
    names
  }
}
    `) as unknown as TypedDocumentString<TableViewQuery, TableViewQueryVariables>;