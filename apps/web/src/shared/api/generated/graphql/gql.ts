/* eslint-disable */
import * as types from './graphql';



/**
 * Map of all GraphQL operations in the project.
 *
 * This map has several performance disadvantages:
 * 1. It is not tree-shakeable, so it will include all operations in the project.
 * 2. It is not minifiable, so the string of a GraphQL query will be multiple times inside the bundle.
 * 3. It does not support dead code elimination, so it will add unused operations.
 *
 * Therefore it is highly recommended to use the babel or swc plugin for production.
 * Learn more about it here: https://the-guild.dev/graphql/codegen/plugins/presets/preset-client#reducing-bundle-size
 */
type Documents = {
    "\n  query OptionChain($key: String!, $names: [FeatureName!]!) {\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n      chain {\n        underlyingId\n        session\n        status\n        expiries {\n          date\n          days\n        }\n        strikes\n      }\n    }\n  }\n": typeof types.OptionChainDocument,
    "\n  query OptionQuotes($key: String!, $expiry: Date!, $date: Date!) {\n    instrument(key: $key, date: $date) {\n      instrumentId\n      chain {\n        quotes(expiry: $expiry) {\n          instrumentId\n          expiry\n          right\n          strike\n          bid\n          ask\n          last\n          volume\n          openInterest\n          iv\n          delta\n          gamma\n          theta\n          vega\n        }\n      }\n    }\n  }\n": typeof types.OptionQuotesDocument,
    "\n  query FeatureCatalogue {\n    catalogue {\n      name\n      kind\n      source\n      dtype\n      format\n      description\n      nullMeaning\n      version\n      group\n      key\n      inputs\n      unit\n      range\n      categories\n      scope\n      owner\n      licence\n    }\n  }\n": typeof types.FeatureCatalogueDocument,
    "\n  query FeatureDistribution($name: FeatureName!) {\n    distribution(name: $name) {\n      name\n      session\n      count\n      nulls\n      quantiles {\n        q\n        value\n      }\n      histogram {\n        lo\n        hi\n        count\n      }\n      categories {\n        value\n        count\n      }\n      unknown {\n        code\n        detail\n      }\n    }\n  }\n": typeof types.FeatureDistributionDocument,
    "\n  query EtfHoldings($key: String!, $top: Int!) {\n    instrument(key: $key) {\n      instrumentId\n      isEtf\n      holdings(top: $top) {\n        asOf\n        source\n        total\n        items {\n          rank\n          name\n          symbol\n          weight\n          assetClass\n          instrument {\n            symbol\n          }\n        }\n      }\n    }\n  }\n": typeof types.EtfHoldingsDocument,
    "\n  query IdeasPage($limit: Int!, $names: [FeatureName!]!) {\n    ideas(limit: $limit) {\n      session\n      priority\n      total\n      screeners {\n        screener {\n          id\n          name\n          owner\n          version\n        }\n        run {\n          runId\n          configVersion\n        }\n        notRun {\n          code\n          detail\n        }\n        picked\n        top {\n          instrumentId\n          score\n          instrument {\n            symbol\n          }\n        }\n      }\n      items {\n        rank\n        instrumentId\n        instrument {\n          symbol\n          features(names: $names) {\n            name\n            value\n            unknown {\n              code\n              detail\n            }\n            info {\n              format\n              unit\n              dtype\n              nullMeaning\n            }\n          }\n        }\n        picks {\n          configId\n          decision\n          score\n          reasons\n          flags\n          criteria {\n            id\n            value\n          }\n          columns {\n            name\n            value\n          }\n        }\n      }\n    }\n  }\n": typeof types.IdeasPageDocument,
    "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": typeof types.InstrumentFactsDocument,
    "\n  query InstrumentEvents($key: String!) {\n    instrument(key: $key) {\n      instrumentId\n      events {\n        table\n        kind\n        date\n        ts\n        values\n      }\n    }\n  }\n": typeof types.InstrumentEventsDocument,
    "\n  query InstrumentPrices($key: String!, $start: Date!) {\n    instrument(key: $key) {\n      instrumentId\n      prices(start: $start) {\n        start\n        end\n        bars {\n          session\n          close\n          volume\n        }\n      }\n    }\n  }\n": typeof types.InstrumentPricesDocument,
    "\n  query InstrumentFeatureValues($key: String!, $names: [FeatureName!]!, $date: Date) {\n    session(date: $date) {\n      date\n    }\n    instrument(key: $key, date: $date) {\n      instrumentId\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": typeof types.InstrumentFeatureValuesDocument,
    "\n  query InstrumentHistory($key: String!, $names: [FeatureName!]!, $start: Date!, $date: Date!) {\n    instrument(key: $key, date: $date) {\n      instrumentId\n      series(names: $names, start: $start) {\n        names\n        points {\n          session\n          values\n        }\n      }\n    }\n  }\n": typeof types.InstrumentHistoryDocument,
    "\n  query ScreenerConfigs {\n    configs(kind: \"screener\") {\n      configId\n      scope\n      kind\n      impl\n      selection\n      hash\n      error\n    }\n  }\n": typeof types.ScreenerConfigsDocument,
    "\n  query MyScreens {\n    myScreens {\n      screenerId\n      status\n      latest\n      hasDraft\n      presetId\n    }\n  }\n": typeof types.MyScreensDocument,
    "\n  query ScreenDetail($id: String!) {\n    screenDetail(screenerId: $id) {\n      screenerId\n      user\n      draft\n      draftError\n      versions\n      latest\n      preset {\n        presetId\n        pinned\n        current\n        rebaseAvailable\n      }\n      hash\n      layers\n      resolved\n      error\n      working\n    }\n  }\n": typeof types.ScreenDetailDocument,
    "\n  query ScreenVersions($id: String!) {\n    screenVersions(screenerId: $id) {\n      version\n      document\n    }\n  }\n": typeof types.ScreenVersionsDocument,
};
const documents: Documents = {
    "\n  query OptionChain($key: String!, $names: [FeatureName!]!) {\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n      chain {\n        underlyingId\n        session\n        status\n        expiries {\n          date\n          days\n        }\n        strikes\n      }\n    }\n  }\n": types.OptionChainDocument,
    "\n  query OptionQuotes($key: String!, $expiry: Date!, $date: Date!) {\n    instrument(key: $key, date: $date) {\n      instrumentId\n      chain {\n        quotes(expiry: $expiry) {\n          instrumentId\n          expiry\n          right\n          strike\n          bid\n          ask\n          last\n          volume\n          openInterest\n          iv\n          delta\n          gamma\n          theta\n          vega\n        }\n      }\n    }\n  }\n": types.OptionQuotesDocument,
    "\n  query FeatureCatalogue {\n    catalogue {\n      name\n      kind\n      source\n      dtype\n      format\n      description\n      nullMeaning\n      version\n      group\n      key\n      inputs\n      unit\n      range\n      categories\n      scope\n      owner\n      licence\n    }\n  }\n": types.FeatureCatalogueDocument,
    "\n  query FeatureDistribution($name: FeatureName!) {\n    distribution(name: $name) {\n      name\n      session\n      count\n      nulls\n      quantiles {\n        q\n        value\n      }\n      histogram {\n        lo\n        hi\n        count\n      }\n      categories {\n        value\n        count\n      }\n      unknown {\n        code\n        detail\n      }\n    }\n  }\n": types.FeatureDistributionDocument,
    "\n  query EtfHoldings($key: String!, $top: Int!) {\n    instrument(key: $key) {\n      instrumentId\n      isEtf\n      holdings(top: $top) {\n        asOf\n        source\n        total\n        items {\n          rank\n          name\n          symbol\n          weight\n          assetClass\n          instrument {\n            symbol\n          }\n        }\n      }\n    }\n  }\n": types.EtfHoldingsDocument,
    "\n  query IdeasPage($limit: Int!, $names: [FeatureName!]!) {\n    ideas(limit: $limit) {\n      session\n      priority\n      total\n      screeners {\n        screener {\n          id\n          name\n          owner\n          version\n        }\n        run {\n          runId\n          configVersion\n        }\n        notRun {\n          code\n          detail\n        }\n        picked\n        top {\n          instrumentId\n          score\n          instrument {\n            symbol\n          }\n        }\n      }\n      items {\n        rank\n        instrumentId\n        instrument {\n          symbol\n          features(names: $names) {\n            name\n            value\n            unknown {\n              code\n              detail\n            }\n            info {\n              format\n              unit\n              dtype\n              nullMeaning\n            }\n          }\n        }\n        picks {\n          configId\n          decision\n          score\n          reasons\n          flags\n          criteria {\n            id\n            value\n          }\n          columns {\n            name\n            value\n          }\n        }\n      }\n    }\n  }\n": types.IdeasPageDocument,
    "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": types.InstrumentFactsDocument,
    "\n  query InstrumentEvents($key: String!) {\n    instrument(key: $key) {\n      instrumentId\n      events {\n        table\n        kind\n        date\n        ts\n        values\n      }\n    }\n  }\n": types.InstrumentEventsDocument,
    "\n  query InstrumentPrices($key: String!, $start: Date!) {\n    instrument(key: $key) {\n      instrumentId\n      prices(start: $start) {\n        start\n        end\n        bars {\n          session\n          close\n          volume\n        }\n      }\n    }\n  }\n": types.InstrumentPricesDocument,
    "\n  query InstrumentFeatureValues($key: String!, $names: [FeatureName!]!, $date: Date) {\n    session(date: $date) {\n      date\n    }\n    instrument(key: $key, date: $date) {\n      instrumentId\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": types.InstrumentFeatureValuesDocument,
    "\n  query InstrumentHistory($key: String!, $names: [FeatureName!]!, $start: Date!, $date: Date!) {\n    instrument(key: $key, date: $date) {\n      instrumentId\n      series(names: $names, start: $start) {\n        names\n        points {\n          session\n          values\n        }\n      }\n    }\n  }\n": types.InstrumentHistoryDocument,
    "\n  query ScreenerConfigs {\n    configs(kind: \"screener\") {\n      configId\n      scope\n      kind\n      impl\n      selection\n      hash\n      error\n    }\n  }\n": types.ScreenerConfigsDocument,
    "\n  query MyScreens {\n    myScreens {\n      screenerId\n      status\n      latest\n      hasDraft\n      presetId\n    }\n  }\n": types.MyScreensDocument,
    "\n  query ScreenDetail($id: String!) {\n    screenDetail(screenerId: $id) {\n      screenerId\n      user\n      draft\n      draftError\n      versions\n      latest\n      preset {\n        presetId\n        pinned\n        current\n        rebaseAvailable\n      }\n      hash\n      layers\n      resolved\n      error\n      working\n    }\n  }\n": types.ScreenDetailDocument,
    "\n  query ScreenVersions($id: String!) {\n    screenVersions(screenerId: $id) {\n      version\n      document\n    }\n  }\n": types.ScreenVersionsDocument,
};

/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query OptionChain($key: String!, $names: [FeatureName!]!) {\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n      chain {\n        underlyingId\n        session\n        status\n        expiries {\n          date\n          days\n        }\n        strikes\n      }\n    }\n  }\n"): typeof import('./graphql').OptionChainDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query OptionQuotes($key: String!, $expiry: Date!, $date: Date!) {\n    instrument(key: $key, date: $date) {\n      instrumentId\n      chain {\n        quotes(expiry: $expiry) {\n          instrumentId\n          expiry\n          right\n          strike\n          bid\n          ask\n          last\n          volume\n          openInterest\n          iv\n          delta\n          gamma\n          theta\n          vega\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').OptionQuotesDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query FeatureCatalogue {\n    catalogue {\n      name\n      kind\n      source\n      dtype\n      format\n      description\n      nullMeaning\n      version\n      group\n      key\n      inputs\n      unit\n      range\n      categories\n      scope\n      owner\n      licence\n    }\n  }\n"): typeof import('./graphql').FeatureCatalogueDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query FeatureDistribution($name: FeatureName!) {\n    distribution(name: $name) {\n      name\n      session\n      count\n      nulls\n      quantiles {\n        q\n        value\n      }\n      histogram {\n        lo\n        hi\n        count\n      }\n      categories {\n        value\n        count\n      }\n      unknown {\n        code\n        detail\n      }\n    }\n  }\n"): typeof import('./graphql').FeatureDistributionDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query EtfHoldings($key: String!, $top: Int!) {\n    instrument(key: $key) {\n      instrumentId\n      isEtf\n      holdings(top: $top) {\n        asOf\n        source\n        total\n        items {\n          rank\n          name\n          symbol\n          weight\n          assetClass\n          instrument {\n            symbol\n          }\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').EtfHoldingsDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query IdeasPage($limit: Int!, $names: [FeatureName!]!) {\n    ideas(limit: $limit) {\n      session\n      priority\n      total\n      screeners {\n        screener {\n          id\n          name\n          owner\n          version\n        }\n        run {\n          runId\n          configVersion\n        }\n        notRun {\n          code\n          detail\n        }\n        picked\n        top {\n          instrumentId\n          score\n          instrument {\n            symbol\n          }\n        }\n      }\n      items {\n        rank\n        instrumentId\n        instrument {\n          symbol\n          features(names: $names) {\n            name\n            value\n            unknown {\n              code\n              detail\n            }\n            info {\n              format\n              unit\n              dtype\n              nullMeaning\n            }\n          }\n        }\n        picks {\n          configId\n          decision\n          score\n          reasons\n          flags\n          criteria {\n            id\n            value\n          }\n          columns {\n            name\n            value\n          }\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').IdeasPageDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').InstrumentFactsDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query InstrumentEvents($key: String!) {\n    instrument(key: $key) {\n      instrumentId\n      events {\n        table\n        kind\n        date\n        ts\n        values\n      }\n    }\n  }\n"): typeof import('./graphql').InstrumentEventsDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query InstrumentPrices($key: String!, $start: Date!) {\n    instrument(key: $key) {\n      instrumentId\n      prices(start: $start) {\n        start\n        end\n        bars {\n          session\n          close\n          volume\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').InstrumentPricesDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query InstrumentFeatureValues($key: String!, $names: [FeatureName!]!, $date: Date) {\n    session(date: $date) {\n      date\n    }\n    instrument(key: $key, date: $date) {\n      instrumentId\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').InstrumentFeatureValuesDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query InstrumentHistory($key: String!, $names: [FeatureName!]!, $start: Date!, $date: Date!) {\n    instrument(key: $key, date: $date) {\n      instrumentId\n      series(names: $names, start: $start) {\n        names\n        points {\n          session\n          values\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').InstrumentHistoryDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query ScreenerConfigs {\n    configs(kind: \"screener\") {\n      configId\n      scope\n      kind\n      impl\n      selection\n      hash\n      error\n    }\n  }\n"): typeof import('./graphql').ScreenerConfigsDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query MyScreens {\n    myScreens {\n      screenerId\n      status\n      latest\n      hasDraft\n      presetId\n    }\n  }\n"): typeof import('./graphql').MyScreensDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query ScreenDetail($id: String!) {\n    screenDetail(screenerId: $id) {\n      screenerId\n      user\n      draft\n      draftError\n      versions\n      latest\n      preset {\n        presetId\n        pinned\n        current\n        rebaseAvailable\n      }\n      hash\n      layers\n      resolved\n      error\n      working\n    }\n  }\n"): typeof import('./graphql').ScreenDetailDocument;
/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query ScreenVersions($id: String!) {\n    screenVersions(screenerId: $id) {\n      version\n      document\n    }\n  }\n"): typeof import('./graphql').ScreenVersionsDocument;


export function graphql(source: string) {
  return (documents as any)[source] ?? {};
}
