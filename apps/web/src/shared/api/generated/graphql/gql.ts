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
    "\n  query FeatureCatalogue {\n    catalogue {\n      name\n      kind\n      source\n      dtype\n      format\n      description\n      nullMeaning\n      version\n      group\n      key\n      inputs\n      unit\n      range\n      categories\n      scope\n      owner\n      licence\n    }\n  }\n": typeof types.FeatureCatalogueDocument,
    "\n  query FeatureDistribution($name: FeatureName!) {\n    distribution(name: $name) {\n      name\n      session\n      count\n      nulls\n      quantiles {\n        q\n        value\n      }\n      histogram {\n        lo\n        hi\n        count\n      }\n      categories {\n        value\n        count\n      }\n      unknown {\n        code\n        detail\n      }\n    }\n  }\n": typeof types.FeatureDistributionDocument,
    "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": typeof types.InstrumentFactsDocument,
    "\n  query ScreenerConfigs {\n    configs(kind: \"screener\") {\n      configId\n      scope\n      kind\n      impl\n      selection\n      hash\n      error\n    }\n  }\n": typeof types.ScreenerConfigsDocument,
    "\n  query MyScreens {\n    myScreens {\n      screenerId\n      status\n      latest\n      hasDraft\n      presetId\n    }\n  }\n": typeof types.MyScreensDocument,
    "\n  query ScreenDetail($id: String!) {\n    screenDetail(screenerId: $id) {\n      screenerId\n      user\n      draft\n      draftError\n      versions\n      latest\n      preset {\n        presetId\n        pinned\n        current\n        rebaseAvailable\n      }\n      hash\n      layers\n      resolved\n      error\n      working\n    }\n  }\n": typeof types.ScreenDetailDocument,
    "\n  query ScreenVersions($id: String!) {\n    screenVersions(screenerId: $id) {\n      version\n      document\n    }\n  }\n": typeof types.ScreenVersionsDocument,
};
const documents: Documents = {
    "\n  query FeatureCatalogue {\n    catalogue {\n      name\n      kind\n      source\n      dtype\n      format\n      description\n      nullMeaning\n      version\n      group\n      key\n      inputs\n      unit\n      range\n      categories\n      scope\n      owner\n      licence\n    }\n  }\n": types.FeatureCatalogueDocument,
    "\n  query FeatureDistribution($name: FeatureName!) {\n    distribution(name: $name) {\n      name\n      session\n      count\n      nulls\n      quantiles {\n        q\n        value\n      }\n      histogram {\n        lo\n        hi\n        count\n      }\n      categories {\n        value\n        count\n      }\n      unknown {\n        code\n        detail\n      }\n    }\n  }\n": types.FeatureDistributionDocument,
    "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": types.InstrumentFactsDocument,
    "\n  query ScreenerConfigs {\n    configs(kind: \"screener\") {\n      configId\n      scope\n      kind\n      impl\n      selection\n      hash\n      error\n    }\n  }\n": types.ScreenerConfigsDocument,
    "\n  query MyScreens {\n    myScreens {\n      screenerId\n      status\n      latest\n      hasDraft\n      presetId\n    }\n  }\n": types.MyScreensDocument,
    "\n  query ScreenDetail($id: String!) {\n    screenDetail(screenerId: $id) {\n      screenerId\n      user\n      draft\n      draftError\n      versions\n      latest\n      preset {\n        presetId\n        pinned\n        current\n        rebaseAvailable\n      }\n      hash\n      layers\n      resolved\n      error\n      working\n    }\n  }\n": types.ScreenDetailDocument,
    "\n  query ScreenVersions($id: String!) {\n    screenVersions(screenerId: $id) {\n      version\n      document\n    }\n  }\n": types.ScreenVersionsDocument,
};

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
export function graphql(source: "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').InstrumentFactsDocument;
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
