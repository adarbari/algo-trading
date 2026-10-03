/**
 * The typed HTTP client: the ONLY code in apps/web that talks HTTP (ADR 0025 rule 4). Paths,
 * parameters and responses are typed from the API's OpenAPI document (generated/schema.ts).
 * Entities and features wrap these calls in TanStack Query hooks; nothing else calls them.
 */
import createClient from 'openapi-fetch';

import { apiBaseUrl } from '@/shared/config';

import type { paths } from './generated/schema';

export const api = createClient<paths>({ baseUrl: apiBaseUrl });

/** An HTTP error from the API, carrying the status and the server's `detail`. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
  }
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
