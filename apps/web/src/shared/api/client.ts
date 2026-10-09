/**
 * The typed HTTP client: the ONLY code in apps/web that talks HTTP (ADR 0025 rule 4). Paths,
 * parameters and responses are typed from the API's OpenAPI document (generated/schema.ts).
 * Entities and features wrap these calls in TanStack Query hooks; nothing else calls them.
 */
import createClient from 'openapi-fetch';

import { apiBaseUrl } from '@/shared/config';

import { accessToken, handleUnauthorized } from './auth';
import type { paths } from './generated/schema';

export const api = createClient<paths>({ baseUrl: apiBaseUrl });

// Every request carries the Supabase access token (ADR 0040); a 401 ends the session.
api.use({
  async onRequest({ request }) {
    const token = await accessToken();
    if (token) request.headers.set('authorization', `Bearer ${token}`);
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401) await handleUnauthorized();
    return response;
  },
});

/** An HTTP error from the API, carrying the status and the server's `detail`. */
export class ApiError extends Error {
  readonly status: number;
  /** The server's message alone (what a user reads), without the status prefix. */
  readonly detail: string;
  /** Seconds the server asked to wait before asking again (`Retry-After`), when it said. */
  readonly retryAfterS: number | undefined;

  constructor(status: number, detail: string, retryAfterS?: number) {
    super(`API ${String(status)}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.retryAfterS = retryAfterS;
  }
}

/** The message to show a user for a failed request: the server's detail, else the error's text. */
export function errorDetail(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  return error instanceof Error ? error.message : String(error);
}

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** The response body, or an ApiError (so TanStack Query sees failures as errors). */
export async function unwrap<T>(request: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (error !== undefined || data === undefined) {
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(response.status, typeof detail === 'string' ? detail : response.statusText);
  }
  return data;
}
