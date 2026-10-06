/**
 * The one GraphQL transport (ADR 0037): `gql(document, variables)` POSTs an operation written
 * with the generated `graphql()` tag to the API's `/graphql` and resolves to its typed data.
 * Entities wrap it in TanStack Query hooks keyed by `queryKeys.gql(operationName, variables)`;
 * no Apollo, no urql (one cache: TanStack Query's).
 *
 * The API answers 200 with `data` and `errors[]`; any error rejects with a `GraphQLRequestError`
 * carrying each error's `extensions.code` (NOT_FOUND, BAD_REQUEST, UNKNOWN_FEATURE, NO_DATA).
 * "Nothing stored yet" is never an error: it is a null field or an UNKNOWN value.
 * Every request carries the Supabase access token as a bearer (ADR 0040); a 401 ends the
 * session (`handleUnauthorized`) and rejects with an `ApiError`.
 */
import { apiBaseUrl } from '@/shared/config';

import { accessToken, handleUnauthorized } from './auth';
import { ApiError } from './client';
import type { TypedDocumentString } from './generated/graphql/graphql';

export interface GraphQLErrorEntry {
  message: string;
  extensions?: { code?: string };
}

/** The operation failed: `codes` are the errors' `extensions.code`, `message` their text. */
export class GraphQLRequestError extends Error {
  readonly codes: readonly string[];

  constructor(errors: readonly GraphQLErrorEntry[]) {
    super(errors.map((e) => e.message).join('; '));
    this.name = 'GraphQLRequestError';
    this.codes = errors.map((e) => e.extensions?.code ?? 'INTERNAL');
  }
}

interface Body<TResult> {
  data?: TResult | null;
  errors?: GraphQLErrorEntry[];
}

/** Runs `document` with `variables`; rejects on an HTTP failure or any GraphQL error. */
export async function gql<TResult, TVariables>(
  document: TypedDocumentString<TResult, TVariables>,
  variables: TVariables,
): Promise<TResult> {
  const token = await accessToken();
  const response = await fetch(`${apiBaseUrl}/graphql`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ query: document.toString(), variables }),
  });
  if (response.status === 401) await handleUnauthorized();
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  const body = (await response.json()) as Body<TResult>;
  if (body.errors?.length) throw new GraphQLRequestError(body.errors);
  if (body.data == null) throw new GraphQLRequestError([{ message: 'no data in the response' }]);
  return body.data;
}
