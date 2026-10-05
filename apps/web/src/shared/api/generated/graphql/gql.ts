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
    "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": typeof types.InstrumentFactsDocument,
};
const documents: Documents = {
    "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n": types.InstrumentFactsDocument,
};

/**
 * The graphql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function graphql(source: "\n  query InstrumentFacts($key: String!, $names: [FeatureName!]!) {\n    session {\n      date\n      isLatest\n      missing\n      referenceSnapshot\n      preSnapshot\n    }\n    instrument(key: $key) {\n      instrumentId\n      symbol\n      name\n      securityType\n      exchange\n      isEtf\n      description\n      referenceSnapshot\n      features(names: $names) {\n        name\n        value\n        unknown {\n          code\n          detail\n        }\n        info {\n          format\n          unit\n          dtype\n          nullMeaning\n        }\n      }\n    }\n  }\n"): typeof import('./graphql').InstrumentFactsDocument;


export function graphql(source: string) {
  return (documents as any)[source] ?? {};
}
