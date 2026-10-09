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
 * session (`handleUnauthorized`) and rejects with an `ApiError`. A 503 is the API shedding load
 * (it queues only a few dozen reads): `gql` waits the `Retry-After` it sent, spread by jitter so
 * refused clients do not return in lockstep, and asks again, up to `BUSY_RETRIES` times, before
 * it rejects (here, not in the query client: the entry chunk has no bytes to spare).
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

const BUSY_RETRIES = 5;

/** The wait before retry number `attempt` (0-based): the server's `Retry-After` (seconds),
 * growing with each try, times a factor between one half and one and a half. */
export function busyDelayMs(retryAfter: string | null, attempt: number): number {
  return (Number(retryAfter) || 1) * 1000 * (1 + attempt / 2) * (0.5 + Math.random());
}

/** Runs `document` with `variables`; rejects on an HTTP failure or any GraphQL error. */
export async function gql<TResult, TVariables>(
  document: TypedDocumentString<TResult, TVariables>,
  variables: TVariables,
): Promise<TResult> {
  const token = await accessToken();
  const init = {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ query: document.toString(), variables }),
  };
  let response = await fetch(`${apiBaseUrl}/graphql`, init);
  for (let attempt = 0; response.status === 503 && attempt < BUSY_RETRIES; attempt++) {
    const wait = busyDelayMs(response.headers.get('retry-after'), attempt);
    await new Promise((resolve) => setTimeout(resolve, wait));
    response = await fetch(`${apiBaseUrl}/graphql`, init);
  }
  if (response.status === 401) await handleUnauthorized();
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  const body = (await response.json()) as Body<TResult>;
  if (body.errors?.length) throw new GraphQLRequestError(body.errors);
  if (body.data == null) throw new GraphQLRequestError([{ message: 'no data in the response' }]);
  return body.data;
}
