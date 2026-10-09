/**
 * The API boundary: the typed REST client, the Supabase session (sign-in, the bearer token), the
 * GraphQL transport `gql()` with the generated `graphql()` tag and its types, the typed site
 * feature names (`feature()`), errors, query keys and the schema types.
 */
export {
  AuthFailure,
  currentSession,
  onUnauthorized,
  signInWithPassword,
  signOutSession,
  subscribeSession,
  type AuthSession,
} from './auth';
export { active } from './active-client';
export { api, ApiError, errorDetail, unwrap } from './client';
export { feature, SITE_FEATURES, type SiteFeature } from './generated/catalogue';
export { graphql, useFragment, type FragmentType } from './generated/graphql';
export type * as gqlTypes from './generated/graphql/graphql';
export type { components, paths } from './generated/schema';
export { gql, GraphQLRequestError } from './graphql';
export { queryKeys } from './query-keys';
export { TestQueryProvider } from './test-provider';
